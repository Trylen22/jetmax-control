#!/usr/bin/env python3
"""
stream.py — Live MJPEG camera stream from JetMax.

Opens an HTTP server on port 8080. View in any browser:
  http://100.65.198.107:8080

RUN:
  source ~/ros/devel/setup.bash && python3 ~/jetmax-control/scripts/vision/stream.py
"""

import threading
import rospy
import cv2
import numpy as np
from sensor_msgs.msg import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8080
latest_jpg = [None]
frame_lock  = threading.Lock()


def image_callback(ros_image):
    img = np.ndarray(
        shape=(ros_image.height, ros_image.width, 3),
        dtype=np.uint8,
        buffer=ros_image.data
    )
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    _, jpg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    with frame_lock:
        latest_jpg[0] = jpg.tobytes()


class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress request logs

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()
        try:
            while True:
                with frame_lock:
                    jpg = latest_jpg[0]
                if jpg:
                    self.wfile.write(
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' +
                        jpg + b'\r\n'
                    )
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    rospy.init_node('stream', anonymous=True)
    rospy.Subscriber('/usb_cam/image_rect_color', Image, image_callback)

    server = HTTPServer(('0.0.0.0', PORT), StreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"Stream live at http://100.65.198.107:{PORT}")
    print("Ctrl+C to stop.\n")

    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        print("Stream stopped.")


if __name__ == '__main__':
    main()
