#!/usr/bin/env python3
"""
belt_vision.py — Vision-guided pick from conveyor belt.

1. Parks arm at WATCH_POS (camera over belt)
2. Detects green block in camera feed
3. Converts pixel offset → mm offset
4. Moves arm to block, grabs it, drops at DROP_ZONE
5. Returns to WATCH_POS and repeats
6. Goes home only if no block seen for IDLE_TIMEOUT seconds

TUNE:
  - GREEN_LOWER / GREEN_UPPER  if green isn't detected
  - MM_PER_PIXEL               if arm lands left/right of block
  - PICK_Z                     if arm is too high/low when grabbing
  - AXIS_FLIP_X / AXIS_FLIP_Y  if arm moves in the wrong direction

RUN:
  source ~/ros/devel/setup.bash && python3 ~/jetmax-control/scripts/vision/belt_vision.py
"""

import rospy
import cv2
import numpy as np
import time
import threading
from sensor_msgs.msg import Image
from jetmax_control.msg import SetJetMax
from std_msgs.msg import Bool

# ── Positions ─────────────────────────────────────────────────────────────────

WATCH_POS  = (-160.0,   0.0, 210.0)   # arm hover over belt (camera watches here)
DROP_ZONE  = (   0.0, -120.0, 100.0)  # where to drop the block
HOME       = (   0.0, -160.0, 200.0)
APPROACH_Z   = 180.0
PICK_Z       = 125.0                  # slightly lower for solid suction contact
IDLE_TIMEOUT = 360	                     # seconds with no block before going home

# ── Vision tuning ─────────────────────────────────────────────────────────────

GREEN_LOWER = np.array([ 35,  40,  50])   # HSV lower — green through cyan/teal
GREEN_UPPER = np.array([110, 255, 255])   # HSV upper — includes light cyan blocks
MIN_AREA    = 500                          # ignore blobs smaller than this (px²)

# ── Pixel → mm conversion ─────────────────────────────────────────────────────
# At z=210 height, tune this if the arm consistently over/undershoots.
# Start with 0.25 and adjust based on where arm actually lands.

MM_PER_PIXEL = 0.25

# ── Axis mapping ──────────────────────────────────────────────────────────────
# If arm moves in the wrong direction, flip these.
AXIS_FLIP_X = 1    # set to -1 to flip left/right
AXIS_FLIP_Y = 1    # set to -1 to flip forward/back

# ── Camera-to-tool offset ─────────────────────────────────────────────────────
# The suction cup is physically ahead of the camera lens.
# Tune TOOL_OFFSET_Y until the suction cup lands centered on the block.
# Negative Y = forward on this arm. 2 inches ≈ 50mm.
TOOL_OFFSET_X = -37.0   # mm — fixed camera-to-sucker offset in X
TOOL_OFFSET_Y =   5.0   # mm — fixed camera-to-sucker offset in Y

# ── State ─────────────────────────────────────────────────────────────────────

latest_frame = None
frame_lock   = threading.Lock()
pub          = None
sucker_pub   = None

# ── ROS ───────────────────────────────────────────────────────────────────────

def image_callback(ros_image):
    global latest_frame
    img = np.ndarray(
        shape=(ros_image.height, ros_image.width, 3),
        dtype=np.uint8,
        buffer=ros_image.data
    )
    with frame_lock:
        latest_frame = img.copy()

def move(x, y, z, duration=1.2):
    msg = SetJetMax()
    msg.x, msg.y, msg.z, msg.duration = float(x), float(y), float(z), float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.3)

def suction(state):
    sucker_pub.publish(Bool(data=state))
    time.sleep(0.3)

# ── Vision ────────────────────────────────────────────────────────────────────

def detect_green(frame):
    """
    Returns (offset_x_mm, offset_y_mm) from image center, or None if not found.
    Positive offset_x = block is to the right in image.
    Positive offset_y = block is lower in image.
    """
    hsv  = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    mask = cv2.erode(mask,  None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_AREA:
        return None

    M  = cv2.moments(largest)
    cx = int(M['m10'] / M['m00'])
    cy = int(M['m01'] / M['m00'])

    img_h, img_w = frame.shape[:2]
    dx_px = cx - img_w // 2
    dy_px = cy - img_h // 2

    # Image X (left/right) maps to arm Y (forward/back on belt)
    # Image Y (up/down)    maps to arm X (left/right of arm)
    arm_dx_mm = dy_px * MM_PER_PIXEL * AXIS_FLIP_X
    arm_dy_mm = dx_px * MM_PER_PIXEL * AXIS_FLIP_Y

    print(f"  [vision] blob center: ({cx},{cy})  offset: ({dx_px}px, {dy_px}px) → arm_dx={arm_dx_mm:.1f}mm  arm_dy={arm_dy_mm:.1f}mm")
    return arm_dx_mm, arm_dy_mm

# ── Main sequence ─────────────────────────────────────────────────────────────

def wait_for_block(timeout):
    """Scan camera for up to `timeout` seconds. Returns confirmed offset or None."""
    wx, wy, wz = WATCH_POS
    deadline = time.time() + timeout
    while time.time() < deadline:
        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None
        if frame is not None:
            result = detect_green(frame)
            if result is not None:
                hits = 0
                for _ in range(5):
                    time.sleep(0.1)
                    with frame_lock:
                        f2 = latest_frame.copy() if latest_frame is not None else None
                    if f2 is not None and detect_green(f2) is not None:
                        hits += 1
                if hits >= 3:
                    return result
        time.sleep(0.1)
    return None

def do_pick(offset):
    """Execute pick-and-place for a confirmed block offset."""
    wx, wy, wz = WATCH_POS
    dx_mm, dy_mm = offset
    pick_x = wx + dx_mm + TOOL_OFFSET_X
    pick_y = wy + dy_mm + TOOL_OFFSET_Y

    print(f"[pick] Block at ({pick_x:.1f}, {pick_y:.1f}) — moving in")
    move(pick_x, pick_y, APPROACH_Z)
    move(pick_x, pick_y, PICK_Z, duration=1.0)
    suction(True)
    time.sleep(0.3)

    move(pick_x, pick_y, APPROACH_Z)

    dx, dy, _ = DROP_ZONE
    move(dx, dy, APPROACH_Z)
    move(dx, dy, PICK_Z, duration=1.0)
    suction(False)
    time.sleep(0.2)
    move(dx, dy, APPROACH_Z)
    print("[pick] Done — back to watch\n")

def run_loop():
    """
    Main belt loop:
    - Always returns to WATCH_POS after each pick
    - Goes home only after IDLE_TIMEOUT seconds with nothing seen
    """
    wx, wy, wz = WATCH_POS
    at_watch = False

    print("\nStarting belt loop. Ctrl+C to stop.\n")
    while not rospy.is_shutdown():
        if not at_watch:
            print("[loop] Moving to watch position...")
            move(wx, wy, wz, duration=1.5)
            at_watch = True

        print(f"[loop] Watching belt (idle timeout: {IDLE_TIMEOUT}s)...")
        offset = wait_for_block(IDLE_TIMEOUT)

        if offset is not None:
            do_pick(offset)
            at_watch = False   # after pick we need to return to watch
        else:
            print(f"[loop] Nothing seen for {IDLE_TIMEOUT}s — going home.")
            move(*HOME, duration=1.5)
            at_watch = False
            # Wait for Enter to restart, or just keep looping
            print("[loop] Press Enter to restart belt watch, or Ctrl+C to quit.")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                raise

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global pub, sucker_pub

    rospy.init_node('belt_vision', anonymous=True)
    pub        = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)
    sucker_pub = rospy.Publisher('/jetmax/end_effector/sucker/command', Bool, queue_size=1)
    rospy.Subscriber('/usb_cam/image_rect_color', Image, image_callback)

    print("Waiting for arm connection...")
    while pub.get_num_connections() == 0:
        time.sleep(0.1)
    print("Connected!\n")

    print("Waiting for camera feed...")
    while latest_frame is None:
        time.sleep(0.1)
    print("Camera ready!\n")

    move(*HOME, duration=1.5)

    try:
        run_loop()
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down — suction off, going home.")
        sucker_pub.publish(Bool(data=False))
        time.sleep(0.3)
        move(*HOME, duration=1.5)

if __name__ == '__main__':
    main()
