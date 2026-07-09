#!/usr/bin/env python3
"""
vision_stream.py — MJPEG camera stream with green-block detection overlay.

Shows bounding boxes, centroid, center crosshair, and offset readout —
same HSV tuning as belt_vision.py.

  http://100.65.198.107:8081/              annotated MJPEG
  http://100.65.198.107:8081/detection.json live detection state

RUN:
  source ~/ros/devel/setup.bash && python3 ~/jetmax-control/scripts/vision/vision_stream.py
"""

import json
import os
import sys
import threading
import time

import cv2
import numpy as np
import rospy
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from sensor_msgs.msg import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "lib"))
from green_detect import annotate_frame, detect_green  # noqa: E402

PORT = 8081
# Keep a positive detection sticky so the UI / pick API don't flicker off
# when a frame briefly fails the HSV mask.
DETECTION_HOLD_SEC = 1.5

latest_jpg = [None]
last_detection = [{"detected": False, "updated": 0}]
held_detection = [None]  # last positive detection dict (with raw fields)
hold_until = [0.0]
frame_lock = threading.Lock()


def image_callback(ros_image):
    img = np.ndarray(
        shape=(ros_image.height, ros_image.width, 3),
        dtype=np.uint8,
        buffer=ros_image.data,
    )
    detection = detect_green(img)
    now = time.time()

    if detection is not None:
        held_detection[0] = detection
        hold_until[0] = now + DETECTION_HOLD_SEC
        display = detection
    elif held_detection[0] is not None and now < hold_until[0]:
        display = held_detection[0]
    else:
        held_detection[0] = None
        display = None

    annotated = annotate_frame(img, display)

    ok, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return

    payload = {
        "detected": display is not None,
        "updated": now,
        "held": display is not None and detection is None,
    }
    if display:
        payload.update({
            "cx": display["cx"],
            "cy": display["cy"],
            "area": display["area"],
            "arm_dx_mm": display["arm_dx_mm"],
            "arm_dy_mm": display["arm_dy_mm"],
        })

    with frame_lock:
        latest_jpg[0] = jpg.tobytes()
        last_detection[0] = payload


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class VisionStreamHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if self.path.startswith("/detection"):
            return
        sys.stdout.write("[vision-stream] %s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/detection.json":
            with frame_lock:
                payload = dict(last_detection[0])
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        try:
            while True:
                with frame_lock:
                    jpg = latest_jpg[0]
                if jpg:
                    self.wfile.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    )
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    rospy.init_node("vision_stream", anonymous=True)
    rospy.Subscriber("/usb_cam/image_rect_color", Image, image_callback)

    server = ThreadedHTTPServer(("0.0.0.0", PORT), VisionStreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host = os.environ.get("JETMAX_HOST", "100.65.198.107")
    print("Vision stream (with green-box overlay)")
    print("=====================================")
    print("  Stream     http://%s:%d/" % (host, PORT))
    print("  Detection  http://%s:%d/detection.json" % (host, PORT))
    print("\nCtrl+C to stop.\n")

    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        print("Vision stream stopped.")


if __name__ == "__main__":
    main()
