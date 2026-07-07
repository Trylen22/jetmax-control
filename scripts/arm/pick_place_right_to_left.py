#!/usr/bin/env python3
import time
import sys

try:
    import hiwonder
except ImportError:
    print("Could not import hiwonder.")
    sys.exit(1)

# -------------------------------------------------
# Basic JetMax staged pick-and-place by servo IDs
# -------------------------------------------------
# IMPORTANT:
# These numbers are starter values only.
# You will likely need to tune them for your robot.
#
# Common idea:
# - servo 1 = base rotate (left/right)
# - other servos = arm joints
# - one servo = gripper open/close
#
# Move one pose at a time, test slowly, and keep clear.
# -------------------------------------------------

MOVE_TIME = 1200
SHORT_PAUSE = 1.4

# ---- Adjust these servo IDs if needed ----
BASE_ID = 1
SHOULDER_ID = 2
ELBOW_ID = 3
WRIST_ID = 4
GRIPPER_ID = 5

# ---- Adjust these values for your robot ----
# Positions are typical serial-servo position values.
# 500 is often center-ish, but verify on your robot.

HOME = {
    BASE_ID: 500,
    SHOULDER_ID: 540,
    ELBOW_ID: 520,
    WRIST_ID: 500,
    GRIPPER_ID: 650,   # open
}

RIGHT_ABOVE_PICK = {
    BASE_ID: 650,      # rotate right
    SHOULDER_ID: 500,
    ELBOW_ID: 540,
    WRIST_ID: 500,
    GRIPPER_ID: 650,   # open
}

RIGHT_DOWN_PICK = {
    BASE_ID: 650,
    SHOULDER_ID: 620,  # lower
    ELBOW_ID: 610,
    WRIST_ID: 500,
    GRIPPER_ID: 650,   # open
}

RIGHT_GRASP = {
    BASE_ID: 650,
    SHOULDER_ID: 620,
    ELBOW_ID: 610,
    WRIST_ID: 500,
    GRIPPER_ID: 430,   # close
}

RIGHT_LIFT = {
    BASE_ID: 650,
    SHOULDER_ID: 500,
    ELBOW_ID: 540,
    WRIST_ID: 500,
    GRIPPER_ID: 430,   # closed
}

LEFT_ABOVE_PLACE = {
    BASE_ID: 350,      # rotate left
    SHOULDER_ID: 500,
    ELBOW_ID: 540,
    WRIST_ID: 500,
    GRIPPER_ID: 430,   # still holding
}

LEFT_DOWN_PLACE = {
    BASE_ID: 350,
    SHOULDER_ID: 620,
    ELBOW_ID: 610,
    WRIST_ID: 500,
    GRIPPER_ID: 430,
}

LEFT_RELEASE = {
    BASE_ID: 350,
    SHOULDER_ID: 620,
    ELBOW_ID: 610,
    WRIST_ID: 500,
    GRIPPER_ID: 650,   # open
}

LEFT_LIFT = {
    BASE_ID: 350,
    SHOULDER_ID: 500,
    ELBOW_ID: 540,
    WRIST_ID: 500,
    GRIPPER_ID: 650,
}


def move_pose(pose, move_time=MOVE_TIME, pause=SHORT_PAUSE):
    for servo_id, pos in pose.items():
        hiwonder.serial_servo.set_position(servo_id, pos, move_time)
    time.sleep(pause)


def main():
    print("Starting right-to-left pick and place...")

    print("Home")
    move_pose(HOME, 1500, 1.8)

    print("Move above pick location on right")
    move_pose(RIGHT_ABOVE_PICK)

    print("Lower to pick")
    move_pose(RIGHT_DOWN_PICK)

    print("Close gripper")
    move_pose(RIGHT_GRASP, 900, 1.2)

    print("Lift object")
    move_pose(RIGHT_LIFT)

    print("Move to left above place location")
    move_pose(LEFT_ABOVE_PLACE, 1500, 1.8)

    print("Lower to place")
    move_pose(LEFT_DOWN_PLACE)

    print("Open gripper / release")
    move_pose(LEFT_RELEASE, 900, 1.2)

    print("Lift away")
    move_pose(LEFT_LIFT)

    print("Return home")
    move_pose(HOME, 1500, 1.8)

    print("Done.")


if __name__ == "__main__":
    main()
