#!/usr/bin/env python3
import time
import csv
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import COORD_LOG_FILE, ensure_data_dir

try:
    import hiwonder
except ImportError:
    print("Could not import hiwonder.")
    sys.exit(1)

# ---------------------------------------------------------
# Commanded-position logger for JetMax pick/place routine
# ---------------------------------------------------------
# These XYZ values are USER-DEFINED REFERENCE COORDINATES,
# not guaranteed measured live coordinates.
#
# You tune these values based on your testing, then reuse them
# later as known good pick/place locations.
# ---------------------------------------------------------

MOVE_TIME_MS = 1200
PAUSE_S = 1.5
LOG_FILE = str(COORD_LOG_FILE)

# ---- Servo IDs: adjust if needed ----
BASE_ID = 1
SHOULDER_ID = 2
ELBOW_ID = 3
WRIST_ID = 4
GRIPPER_ID = 5

# ---- Gripper values: adjust if needed ----
GRIPPER_OPEN = 650
GRIPPER_CLOSED = 430

# ---------------------------------------------------------
# Reference coordinate table
# Units here are whatever YOU choose to use consistently.
# A common choice is millimeters for x,y,z.
# These are "commanded reference coordinates" for your notes.
# ---------------------------------------------------------
POSE_COORDS = {
    "HOME":              {"x": 0,   "y": 180, "z": 120},
    "RIGHT_ABOVE_PICK":  {"x": 120, "y": 140, "z":  90},
    "RIGHT_PICK":        {"x": 120, "y": 140, "z":  35},
    "RIGHT_LIFT":        {"x": 120, "y": 140, "z":  90},
    "LEFT_ABOVE_PLACE":  {"x":-120, "y": 140, "z":  90},
    "LEFT_PLACE":        {"x":-120, "y": 140, "z":  35},
    "LEFT_LIFT":         {"x":-120, "y": 140, "z":  90},
}

# ---------------------------------------------------------
# Servo pose table
# These are starter values only. Tune them on your robot.
# ---------------------------------------------------------
POSE_SERVOS = {
    "HOME": {
        BASE_ID: 500,
        SHOULDER_ID: 540,
        ELBOW_ID: 520,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_OPEN,
    },
    "RIGHT_ABOVE_PICK": {
        BASE_ID: 650,
        SHOULDER_ID: 500,
        ELBOW_ID: 540,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_OPEN,
    },
    "RIGHT_PICK": {
        BASE_ID: 650,
        SHOULDER_ID: 620,
        ELBOW_ID: 610,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_OPEN,
    },
    "RIGHT_GRASP": {
        BASE_ID: 650,
        SHOULDER_ID: 620,
        ELBOW_ID: 610,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_CLOSED,
    },
    "RIGHT_LIFT": {
        BASE_ID: 650,
        SHOULDER_ID: 500,
        ELBOW_ID: 540,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_CLOSED,
    },
    "LEFT_ABOVE_PLACE": {
        BASE_ID: 350,
        SHOULDER_ID: 500,
        ELBOW_ID: 540,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_CLOSED,
    },
    "LEFT_PLACE": {
        BASE_ID: 350,
        SHOULDER_ID: 620,
        ELBOW_ID: 610,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_CLOSED,
    },
    "LEFT_RELEASE": {
        BASE_ID: 350,
        SHOULDER_ID: 620,
        ELBOW_ID: 610,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_OPEN,
    },
    "LEFT_LIFT": {
        BASE_ID: 350,
        SHOULDER_ID: 500,
        ELBOW_ID: 540,
        WRIST_ID: 500,
        GRIPPER_ID: GRIPPER_OPEN,
    },
}

def ensure_log_header():
    try:
        with open(LOG_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "pose_name",
                "x", "y", "z",
                "base", "shoulder", "elbow", "wrist", "gripper"
            ])
    except FileExistsError:
        pass

def log_pose(pose_name, pose_servos):
    coords = POSE_COORDS.get(pose_name, {"x": "", "y": "", "z": ""})
    row = [
        datetime.now().isoformat(timespec="seconds"),
        pose_name,
        coords["x"], coords["y"], coords["z"],
        pose_servos.get(BASE_ID, ""),
        pose_servos.get(SHOULDER_ID, ""),
        pose_servos.get(ELBOW_ID, ""),
        pose_servos.get(WRIST_ID, ""),
        pose_servos.get(GRIPPER_ID, ""),
    ]

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

def print_pose_info(pose_name, pose_servos):
    coords = POSE_COORDS.get(pose_name)
    print("=" * 55)
    print(f"POSE: {pose_name}")

    if coords:
        print(f"Commanded coordinates -> X:{coords['x']}  Y:{coords['y']}  Z:{coords['z']}")
    else:
        print("Commanded coordinates -> not defined for this pose")

    print(
        "Servo targets -> "
        f"base:{pose_servos.get(BASE_ID)}  "
        f"shoulder:{pose_servos.get(SHOULDER_ID)}  "
        f"elbow:{pose_servos.get(ELBOW_ID)}  "
        f"wrist:{pose_servos.get(WRIST_ID)}  "
        f"gripper:{pose_servos.get(GRIPPER_ID)}"
    )

def move_pose(pose_name, move_time_ms=MOVE_TIME_MS, pause_s=PAUSE_S):
    pose_servos = POSE_SERVOS[pose_name]
    print_pose_info(pose_name, pose_servos)

    for servo_id, position in pose_servos.items():
        hiwonder.serial_servo.set_position(servo_id, position, move_time_ms)

    log_pose(pose_name, pose_servos)
    time.sleep(pause_s)

def main():
    ensure_data_dir()
    ensure_log_header()

    print("Starting logged pick-and-place routine...")
    print(f"Logging to: {LOG_FILE}")

    move_pose("HOME", 1500, 1.8)
    move_pose("RIGHT_ABOVE_PICK")
    move_pose("RIGHT_PICK")
    move_pose("RIGHT_GRASP", 900, 1.2)
    move_pose("RIGHT_LIFT")
    move_pose("LEFT_ABOVE_PLACE", 1500, 1.8)
    move_pose("LEFT_PLACE")
    move_pose("LEFT_RELEASE", 900, 1.2)
    move_pose("LEFT_LIFT")
    move_pose("HOME", 1500, 1.8)

    print("Done.")
    print(f"Review the saved coordinate log here: {LOG_FILE}")

if __name__ == "__main__":
    main()
