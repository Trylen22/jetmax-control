#!/usr/bin/env python3
"""
plc_sim.py — PLC register simulator for JetMax pick-and-place.

Simulates what will eventually come from the Do-More PLC over Modbus TCP.
Type a command number into the terminal and the arm executes the matching
movement sequence — the same dispatcher will be used when the real PLC is wired in.

COMMANDS
────────
  1   Pick from position A      (front-left)
  2   Pick from position B      (front-center)
  3   Pick from position C      (front-right)
  4   Place at drop zone
  5   Home
  0   Emergency stop / home now

SWAPPING IN THE REAL PLC
────────────────────────
  Replace the input loop at the bottom with a call to watch.py's register
  polling logic. When MHR9 changes to a new value, call dispatch(new_value).
  Everything else stays the same.

RUN
───
  source ~/ros/devel/setup.bash && python3 ~/jetmax-control/scripts/plc/plc_sim.py
"""

import rospy
import time
import threading
from jetmax_control.msg import SetJetMax, JetMax as JetMaxState
from std_msgs.msg import Bool

# ── Arm positions (x, y, z) in mm ─────────────────────────────────────────────
# Tune these once the arm is physically placed on the map.

HOME        = (  0, -160,  200)   # safe raised position
PICK_A      = (-80, -180,  120)   # front-left pick point
PICK_B      = (  0, -200,  120)   # front-center pick point
PICK_C      = ( 80, -180,  120)   # front-right pick point
DROP_ZONE   = (  0, -130,  130)   # where parts get placed

# Saved positions from wasd_control.py
BLOCK_POS_1 = (-200.0, -20.0, 130.0)  # block_pos_1 — arm touching block

APPROACH_Z  = 180                 # z height to travel to before descending to pick
PICK_Z      = 100                 # z height to actually grab/release

# ── State ─────────────────────────────────────────────────────────────────────

current_pos = list(HOME)
pos_lock    = threading.Lock()
pub         = None
sucker_pub  = None

# ── ROS helpers ───────────────────────────────────────────────────────────────

def status_callback(msg):
    with pos_lock:
        current_pos[0] = msg.x
        current_pos[1] = msg.y
        current_pos[2] = msg.z

def move(x, y, z, duration=1.2):
    """Send a single position command and wait for the move to finish."""
    msg = SetJetMax()
    msg.x, msg.y, msg.z, msg.duration = float(x), float(y), float(z), float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.3)

def suction(state):
    """Turn suction on (True) or off (False)."""
    sucker_pub.publish(Bool(data=state))
    time.sleep(0.3)

# ── Movement sequences ────────────────────────────────────────────────────────

def go_home():
    print("  → Home")
    move(*HOME, duration=1.5)

def pick_and_place(pick_pos, label=""):
    """
    Standard pick-and-place sequence:
      1. Raise to approach height above pick point
      2. Descend to pick height
      3. (suction/gripper would activate here)
      4. Raise back up
      5. Move over drop zone
      6. Descend to release height
      7. (suction/gripper releases here)
      8. Return home
    """
    px, py, _ = pick_pos

    print(f"  → Approach {label}")
    move(px, py, APPROACH_Z)

    print(f"  → Pick {label}")
    move(px, py, PICK_Z)
    suction(True)     # suction ON — grab object

    print("  → Lift")
    move(px, py, APPROACH_Z)

    print("  → Move to drop zone")
    dx, dy, _ = DROP_ZONE
    move(dx, dy, APPROACH_Z)

    print("  → Place")
    move(dx, dy, PICK_Z)
    suction(False)    # suction OFF — release object

    print("  → Retract")
    move(dx, dy, APPROACH_Z)

    print("  → Home")
    go_home()

# ── Command dispatcher ────────────────────────────────────────────────────────
# This is the function that will be called by both the keyboard sim
# AND the real Modbus watcher when the PLC is connected.

def pick_block_pos_1():
    """
    Pick sequence for block_pos_1.
    Approaches from above, descends to exact saved position, 
    activates suction, lifts, moves to drop zone, releases.
    """
    bx, by, bz = BLOCK_POS_1

    print("  → Approach block_pos_1")
    move(bx, by, bz + 60)          # approach 60mm above the block

    print("  → Descend to block")
    move(bx, by, bz, duration=1.0) # descend to exact touch position
    suction(True)                   # suction ON — grab block
    time.sleep(0.3)                 # brief dwell to confirm grip

    print("  → Lift")
    move(bx, by, bz + 60)

    print("  → Move to drop zone")
    dx, dy, _ = DROP_ZONE
    move(dx, dy, APPROACH_Z)

    print("  → Place")
    move(dx, dy, PICK_Z)
    suction(False)                  # suction OFF — release block
    time.sleep(0.2)

    print("  → Retract")
    move(dx, dy, APPROACH_Z)

    print("  → Home")
    go_home()

def return_block_pos_1():
    """
    Reverse of pick_block_pos_1.
    Picks from drop zone and places back at block_pos_1.
    """
    bx, by, bz = BLOCK_POS_1
    dx, dy, _ = DROP_ZONE

    print("  → Approach drop zone")
    move(dx, dy, APPROACH_Z)

    print("  → Descend to drop zone")
    move(dx, dy, PICK_Z - 15, duration=1.0)
    suction(True)                   # suction ON — grab from drop zone
    time.sleep(0.3)

    print("  → Lift")
    move(dx, dy, APPROACH_Z)

    print("  → Move to block_pos_1")
    move(bx, by, bz + 60)

    print("  → Descend to block_pos_1")
    move(bx, by, bz, duration=1.0)
    suction(False)                  # suction OFF — release at original position
    time.sleep(0.2)

    print("  → Retract")
    move(bx, by, bz + 60)

    print("  → Home")
    go_home()

COMMANDS = {
    1: ("Pick A  (front-left)",    lambda: pick_and_place(PICK_A,    "A")),
    2: ("Pick B  (front-center)",  lambda: pick_and_place(PICK_B,    "B")),
    3: ("Pick C  (front-right)",   lambda: pick_and_place(PICK_C,    "C")),
    4: ("Place at drop zone",      lambda: pick_and_place(DROP_ZONE, "drop zone")),
    5: ("Home",                    go_home),
    6: ("Pick block_pos_1 → drop zone",   pick_block_pos_1),
    7: ("Drop zone → return block_pos_1", return_block_pos_1),
    0: ("E-Stop / Home",           go_home),
}

def dispatch(value: int):
    """Map a register value to an arm sequence and execute it."""
    if value not in COMMANDS:
        print(f"  [!] Unknown command: {value}  (valid: {list(COMMANDS.keys())})")
        return
    label, fn = COMMANDS[value]
    print(f"\n[CMD {value}] {label}")
    fn()
    print(f"[CMD {value}] Done\n")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global pub, sucker_pub

    rospy.init_node('plc_sim', anonymous=True)
    pub = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)
    sucker_pub = rospy.Publisher('/jetmax/end_effector/sucker/command', Bool, queue_size=1)
    rospy.Subscriber('/jetmax/status', JetMaxState, status_callback)

    print("Waiting for jetmax_control to connect...")
    while pub.get_num_connections() == 0:
        time.sleep(0.1)
    print("Connected!\n")

    # Move to home on start
    go_home()

    # Print menu
    print("─────────────────────────────────────")
    print("  JetMax PLC Simulator")
    print("  (swap input loop for Modbus later)")
    print("─────────────────────────────────────")
    for k, (label, _) in sorted(COMMANDS.items()):
        print(f"  {k}  —  {label}")
    print("  q  —  Quit")
    print("─────────────────────────────────────\n")

    # ── Input loop (replace this block with Modbus register polling) ──────────
    while not rospy.is_shutdown():
        try:
            raw = input("Enter command: ").strip().lower()
            if raw == 'q':
                break
            if not raw.isdigit():
                print("  Enter a number or 'q' to quit.")
                continue
            dispatch(int(raw))
        except (EOFError, KeyboardInterrupt):
            break
    # ─────────────────────────────────────────────────────────────────────────

    print("\nShutting down — returning home.")
    go_home()

if __name__ == "__main__":
    main()
