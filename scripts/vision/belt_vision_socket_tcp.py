#!/usr/bin/env python3
"""
belt_vision_socket_tcp.py

Ethernet version of belt_vision using a plain TCP socket between the
Micro820 PLC and the Jetson/JetMax through an Ethernet switch.

Protocol:
  PLC -> Robot:
    "START\n"      begin belt vision loop
    "STOP\n"       stop belt vision loop and return home
    "STATUS\n"     request current status

  Robot -> PLC:
    "IDLE\n"
    "RUNNING\n"
    "DONE\n"
    "FAULT\n"

Recommended PLC bit flow:
  HMI button writes BOOL tag RobotCmd.
  If RobotCmd transitions TRUE, PLC sends START.
  If RobotCmd transitions FALSE, PLC sends STOP.
"""

import socket
import threading
import time

import cv2
import hiwonder
import numpy as np
import rospy
from jetmax_control.msg import SetJetMax
from sensor_msgs.msg import Image
from std_msgs.msg import Bool


WATCH_POS = (-160.0, 0.0, 210.0)
HOME = (0.0, -160.0, 200.0)
APPROACH_Z = 180.0
PICK_Z = 124.0
IDLE_TIMEOUT = 360
PLACE_Z = PICK_Z

GREEN_LOWER = np.array([35, 40, 50])   # green through cyan/teal
GREEN_UPPER = np.array([110, 255, 255])
MIN_AREA = 500

MM_PER_PIXEL = 0.25
AXIS_FLIP_X = 1
AXIS_FLIP_Y = 1

TOOL_OFFSET_X = -37.0
TOOL_OFFSET_Y = 5.0
WRIST_HOME_ANGLE = 90
WRIST_MOVE_TIME = 0.5

# Eight-place pallet recipe. Each detected green block is picked from the
# camera-detected source location and then placed into the next target below.
PLACE_TARGETS = [
    (20.0, -142.0, 113.0, 75.0),   # blk_p_1
    (20.0, -182.0, 113.0, 77.0),   # blk_p_2
    (-14.0, -182.0, 113.0, 152.0), # blk_p_3
    (-14.0, -138.0, 113.0, 150.0), # blk_p_4
    (20.0, -142.0, 143.0, 75.0),   # blk_p_5
    (20.0, -182.0, 143.0, 77.0),   # blk_p_6
    (-14.0, -182.0, 143.0, 152.0), # blk_p_7
    (-14.0, -138.0, 143.0, 150.0), # blk_p_8
]

TCP_BIND_HOST = "0.0.0.0"
TCP_PORT = 12000
SOCKET_BUFFER_SIZE = 1024

STATUS_IDLE = "IDLE"
STATUS_RUNNING = "RUNNING"
STATUS_DONE = "DONE"
STATUS_FAULT = "FAULT"

latest_frame = None
frame_lock = threading.Lock()
pub = None
sucker_pub = None

command_lock = threading.Lock()
robot_cmd = False
robot_status = STATUS_IDLE
client_socket = None


def set_robot_cmd(value):
    global robot_cmd
    with command_lock:
        robot_cmd = bool(value)


def get_robot_cmd():
    with command_lock:
        return robot_cmd


def set_robot_status(value):
    global robot_status
    with command_lock:
        robot_status = value


def get_robot_status():
    with command_lock:
        return robot_status


def send_status_line(sock, status_text):
    try:
        sock.sendall(f"{status_text}\n".encode("ascii"))
    except OSError:
        pass


def image_callback(ros_image):
    global latest_frame
    img = np.ndarray(
        shape=(ros_image.height, ros_image.width, 3),
        dtype=np.uint8,
        buffer=ros_image.data,
    )
    with frame_lock:
        latest_frame = img.copy()


def move(x, y, z, duration=1.2):
    msg = SetJetMax()
    msg.x = float(x)
    msg.y = float(y)
    msg.z = float(z)
    msg.duration = float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.3)


def suction(state):
    sucker_pub.publish(Bool(data=state))
    time.sleep(0.3)


def rotate_wrist(angle_degrees, duration=WRIST_MOVE_TIME):
    hiwonder.pwm_servo2.set_position(angle_degrees, duration)
    time.sleep(duration + 0.1)


def detect_green(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_AREA:
        return None

    moments = cv2.moments(largest)
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])

    img_h, img_w = frame.shape[:2]
    dx_px = cx - img_w // 2
    dy_px = cy - img_h // 2

    arm_dx_mm = dy_px * MM_PER_PIXEL * AXIS_FLIP_X
    arm_dy_mm = dx_px * MM_PER_PIXEL * AXIS_FLIP_Y

    print(
        f"  [vision] blob center: ({cx},{cy}) offset: ({dx_px}px, {dy_px}px) "
        f"-> arm_dx={arm_dx_mm:.1f}mm arm_dy={arm_dy_mm:.1f}mm"
    )
    return arm_dx_mm, arm_dy_mm


def wait_for_block(timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not get_robot_cmd():
            return None

        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None

        if frame is not None:
            result = detect_green(frame)
            if result is not None:
                hits = 0
                for _ in range(5):
                    time.sleep(0.1)
                    if not get_robot_cmd():
                        return None
                    with frame_lock:
                        confirm_frame = (
                            latest_frame.copy() if latest_frame is not None else None
                        )
                    if confirm_frame is not None and detect_green(confirm_frame) is not None:
                        hits += 1
                if hits >= 3:
                    return result

        time.sleep(0.1)

    return None


def do_pick_and_place(offset, place_target, block_number):
    watch_x, watch_y, _ = WATCH_POS
    dx_mm, dy_mm = offset
    pick_x = watch_x + dx_mm + TOOL_OFFSET_X
    pick_y = watch_y + dy_mm + TOOL_OFFSET_Y
    drop_x, drop_y, drop_z, rotate_angle = place_target

    print(
        f"[pick] Block {block_number} pickup at ({pick_x:.1f}, {pick_y:.1f}) "
        f"-> place at ({drop_x:.1f}, {drop_y:.1f}, {drop_z:.1f}) "
        f"with wrist angle {rotate_angle:.1f}"
    )
    move(pick_x, pick_y, APPROACH_Z)
    move(pick_x, pick_y, PICK_Z, duration=1.0)
    suction(True)
    time.sleep(0.3)

    move(pick_x, pick_y, APPROACH_Z)
    rotate_wrist(rotate_angle)

    move(drop_x, drop_y, APPROACH_Z)
    move(drop_x, drop_y, drop_z, duration=1.0)
    suction(False)
    time.sleep(0.2)
    move(drop_x, drop_y, APPROACH_Z)
    rotate_wrist(WRIST_HOME_ANGLE)
    print(f"[pick] Block {block_number} placed\n")


def run_loop():
    watch_x, watch_y, watch_z = WATCH_POS
    block_index = 0

    set_robot_status(STATUS_RUNNING)
    print("\nStarting 8-block placement recipe from TCP command.\n")
    while not rospy.is_shutdown() and get_robot_cmd() and block_index < len(PLACE_TARGETS):
        print(f"[loop] Moving to watch position for block {block_index + 1}...")
        move(watch_x, watch_y, watch_z, duration=1.5)

        print(
            f"[loop] Watching belt for block {block_index + 1} "
            f"(idle timeout: {IDLE_TIMEOUT}s)..."
        )
        offset = wait_for_block(IDLE_TIMEOUT)

        if offset is not None:
            do_pick_and_place(offset, PLACE_TARGETS[block_index], block_index + 1)
            block_index += 1
        else:
            if get_robot_cmd():
                print(f"[loop] Nothing seen for {IDLE_TIMEOUT}s - going home.")
            else:
                print("[loop] RobotCmd turned off - going home.")
            move(*HOME, duration=1.5)
            set_robot_status(STATUS_DONE if get_robot_cmd() else STATUS_IDLE)
            return

    move(*HOME, duration=1.5)
    if block_index == len(PLACE_TARGETS):
        print(f"[loop] Completed all {len(PLACE_TARGETS)} block placements.")
        set_robot_cmd(False)
        set_robot_status(STATUS_DONE)
    else:
        set_robot_status(STATUS_IDLE)


def socket_server_loop():
    global client_socket

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((TCP_BIND_HOST, TCP_PORT))
    server_sock.listen(1)
    server_sock.settimeout(1.0)

    print(f"TCP command server listening on {TCP_BIND_HOST}:{TCP_PORT}")

    while not rospy.is_shutdown():
        try:
            sock, addr = server_sock.accept()
        except socket.timeout:
            continue

        client_socket = sock
        print(f"PLC connected from {addr[0]}:{addr[1]}")
        sock.settimeout(1.0)
        buffer = b""

        try:
            while not rospy.is_shutdown():
                try:
                    data = sock.recv(SOCKET_BUFFER_SIZE)
                except socket.timeout:
                    continue

                if not data:
                    break

                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    command = line.decode("ascii", errors="ignore").strip().upper()

                    if command == "START":
                        set_robot_cmd(True)
                        send_status_line(sock, STATUS_RUNNING)
                    elif command == "STOP":
                        set_robot_cmd(False)
                        send_status_line(sock, STATUS_IDLE)
                    elif command == "STATUS":
                        send_status_line(sock, get_robot_status())
                    else:
                        send_status_line(sock, "UNKNOWN")
        except OSError:
            pass
        finally:
            print("PLC socket disconnected")
            try:
                sock.close()
            except OSError:
                pass
            client_socket = None
            set_robot_cmd(False)

    server_sock.close()


def main():
    global pub, sucker_pub

    rospy.init_node("belt_vision_socket_tcp", anonymous=True)
    pub = rospy.Publisher("/jetmax/command", SetJetMax, queue_size=1)
    sucker_pub = rospy.Publisher(
        "/jetmax/end_effector/sucker/command", Bool, queue_size=1
    )
    rospy.Subscriber("/usb_cam/image_rect_color", Image, image_callback)

    server_thread = threading.Thread(target=socket_server_loop, daemon=True)
    server_thread.start()

    print("Waiting for arm connection...")
    while pub.get_num_connections() == 0:
        time.sleep(0.1)
    print("Connected!\n")

    print("Waiting for camera feed...")
    while latest_frame is None:
        time.sleep(0.1)
    print("Camera ready!\n")

    rotate_wrist(WRIST_HOME_ANGLE)
    move(*HOME, duration=1.5)
    set_robot_status(STATUS_IDLE)

    try:
        print(f"Waiting for PLC TCP commands on port {TCP_PORT}...")
        while not rospy.is_shutdown():
            if get_robot_cmd():
                try:
                    run_loop()
                except Exception:
                    set_robot_status(STATUS_FAULT)
                    if client_socket is not None:
                        send_status_line(client_socket, STATUS_FAULT)
                    raise

                if client_socket is not None:
                    send_status_line(client_socket, get_robot_status())

                while not rospy.is_shutdown() and get_robot_cmd():
                    time.sleep(0.05)
            else:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down - suction off, going home.")
        set_robot_cmd(False)
        set_robot_status(STATUS_IDLE)
        rotate_wrist(WRIST_HOME_ANGLE)
        sucker_pub.publish(Bool(data=False))
        time.sleep(0.3)
        move(*HOME, duration=1.5)


if __name__ == "__main__":
    main()
