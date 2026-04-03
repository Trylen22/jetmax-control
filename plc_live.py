#!/usr/bin/env python3
"""
plc_live.py — Live Allen Bradley Micro820 connection via EtherNet/IP.

Polls a tag on the PLC every 0.5 seconds.
When the value changes, dispatches the arm movement command.

PLC SETUP (tell the AB programmer):
  1. Create an INT tag named "RobotCmd" in their ladder program
  2. Write command values to it:
       6 = pick block_pos_1 → drop zone
       7 = drop zone → return block_pos_1
       5 = home
       0 = do nothing / idle

RUN:
  source ~/ros/devel/setup.bash && python3 ~/plc_live.py

TEST WITHOUT PLC:
  python3 ~/plc_live.py --sim
  (runs in simulation mode, prompts for input like plc_sim.py)
"""

import argparse
import rospy
import time
import threading
from jetmax_control.msg import SetJetMax, JetMax as JetMaxState
from std_msgs.msg import Bool

# ── PLC Settings ──────────────────────────────────────────────────────────────

PLC_IP      = "192.168.1.10"   # Allen Bradley Micro820 IP
TAG_NAME    = "RobotCmd"       # INT tag name in their ladder program
POLL_MS     = 0.5              # how often to check the tag (seconds)

# ── Arm positions ─────────────────────────────────────────────────────────────

HOME        = (  0, -160,  200)
DROP_ZONE   = (  0, -130,  130)
BLOCK_POS_1 = (-200.0, -20.0, 130.0)
APPROACH_Z  = 180
PICK_Z      = 100

# ── State ─────────────────────────────────────────────────────────────────────

current_pos = [0, 0, 0]
pos_lock    = threading.Lock()
pub         = None
sucker_pub  = None

# ── ROS ───────────────────────────────────────────────────────────────────────

def status_callback(msg):
    with pos_lock:
        current_pos[0] = msg.x
        current_pos[1] = msg.y
        current_pos[2] = msg.z

def move(x, y, z, duration=1.2):
    msg = SetJetMax()
    msg.x, msg.y, msg.z, msg.duration = float(x), float(y), float(z), float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.3)

def suction(state):
    sucker_pub.publish(Bool(data=state))
    time.sleep(0.3)

# ── Movement sequences ────────────────────────────────────────────────────────

def go_home():
    print("  → Home")
    move(*HOME, duration=1.5)

def pick_block_pos_1():
    bx, by, bz = BLOCK_POS_1
    print("  → Approach block_pos_1")
    move(bx, by, bz + 60)
    print("  → Descend")
    move(bx, by, bz, duration=1.0)
    suction(True)
    time.sleep(0.3)
    print("  → Lift")
    move(bx, by, bz + 60)
    print("  → Drop zone")
    dx, dy, _ = DROP_ZONE
    move(dx, dy, APPROACH_Z)
    print("  → Place")
    move(dx, dy, PICK_Z)
    suction(False)
    time.sleep(0.2)
    move(dx, dy, APPROACH_Z)
    go_home()

def return_block_pos_1():
    bx, by, bz = BLOCK_POS_1
    dx, dy, _ = DROP_ZONE
    print("  → Approach drop zone")
    move(dx, dy, APPROACH_Z)
    print("  → Descend")
    move(dx, dy, PICK_Z - 15, duration=1.0)
    suction(True)
    time.sleep(0.3)
    print("  → Lift")
    move(dx, dy, APPROACH_Z)
    print("  → block_pos_1")
    move(bx, by, bz + 60)
    print("  → Place")
    move(bx, by, bz, duration=1.0)
    suction(False)
    time.sleep(0.2)
    move(bx, by, bz + 60)
    go_home()

# ── Dispatcher ────────────────────────────────────────────────────────────────

COMMANDS = {
    5: ("Home",                          go_home),
    6: ("Pick block_pos_1 → drop zone",  pick_block_pos_1),
    7: ("Drop zone → return block_pos_1",return_block_pos_1),
    0: ("Idle",                          None),
}

def dispatch(value):
    if value not in COMMANDS:
        print(f"  [!] Unknown command: {value}")
        return
    label, fn = COMMANDS[value]
    if fn is None:
        return
    print(f"\n[CMD {value}] {label}")
    fn()
    print(f"[CMD {value}] Done\n")

# ── PLC polling loop ──────────────────────────────────────────────────────────

def plc_loop():
    from pylogix import PLC
    prev = 0
    print(f"Connecting to PLC at {PLC_IP}...")
    with PLC() as comm:
        comm.IPAddress = PLC_IP
        comm.Micro800 = True   # required for Micro820 / Micro800 series
        # Test connection
        test = comm.Read(TAG_NAME)
        if test.Status != 'Success':
            print(f"[ERROR] Could not read tag '{TAG_NAME}': {test.Status}")
            print("Check PLC IP, tag name, and that EtherNet/IP is enabled.")
            return
        print(f"Connected! Reading tag '{TAG_NAME}' every {POLL_MS}s\n")
        while not rospy.is_shutdown():
            result = comm.Read(TAG_NAME)
            if result.Status == 'Success':
                val = int(result.Value)
                if val != prev:
                    print(f"[PLC] {TAG_NAME} changed: {prev} → {val}")
                    dispatch(val)
                    prev = val
            else:
                print(f"[WARN] Read failed: {result.Status}")
            time.sleep(POLL_MS)

# ── Sim loop (no PLC needed) ──────────────────────────────────────────────────

def sim_loop():
    print("─────────────────────────────────────")
    print("  SIMULATION MODE (no PLC)")
    print("─────────────────────────────────────")
    for k, (label, _) in sorted(COMMANDS.items()):
        if k != 0:
            print(f"  {k}  —  {label}")
    print("  q  —  Quit")
    print("─────────────────────────────────────\n")
    while not rospy.is_shutdown():
        try:
            raw = input("Enter command: ").strip().lower()
            if raw == 'q':
                break
            if raw.isdigit():
                dispatch(int(raw))
        except (EOFError, KeyboardInterrupt):
            break

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global pub, sucker_pub

    parser = argparse.ArgumentParser()
    parser.add_argument('--sim', action='store_true', help='Run in simulation mode without PLC')
    args = parser.parse_args()

    rospy.init_node('plc_live', anonymous=True)
    pub = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)
    sucker_pub = rospy.Publisher('/jetmax/end_effector/sucker/command', Bool, queue_size=1)
    rospy.Subscriber('/jetmax/status', JetMaxState, status_callback)

    print("Waiting for jetmax_control to connect...")
    while pub.get_num_connections() == 0:
        time.sleep(0.1)
    print("Connected!\n")

    go_home()

    if args.sim:
        sim_loop()
    else:
        plc_loop()

    print("Shutting down — returning home.")
    go_home()

if __name__ == "__main__":
    main()
