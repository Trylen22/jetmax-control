#!/usr/bin/env python3
"""
wasd_control.py — Keyboard controller for JetMax robotic arm.

Controls:
  W / S     — Forward / Back  (Y axis)
  A / D     — Left / Right    (X axis)
  R / F     — Up / Down       (Z axis)
  SPACE     — Return to home
  P         — Save current position (prompted for a name)
  G         — Go to a saved position (prompted for slot number)
  L         — List all saved positions
  Q         — Quit
"""
import curses
import rospy
import threading
import time
import json
import os
from jetmax_control.msg import SetJetMax, JetMax as JetMaxState

# --- Settings ---
STEP = 10          # mm per keypress
DURATION = 0.3     # seconds per move (lower = snappier)
HOME = (0, -160, 200)
SAVED_POSITIONS_FILE = os.path.expanduser('~/saved_positions.json')

# --- State ---
position = list(HOME)
position_lock = threading.Lock()
saved_positions = []

def load_positions():
    global saved_positions
    if os.path.exists(SAVED_POSITIONS_FILE):
        with open(SAVED_POSITIONS_FILE, 'r') as f:
            saved_positions = json.load(f)

def save_positions():
    with open(SAVED_POSITIONS_FILE, 'w') as f:
        json.dump(saved_positions, f, indent=2)

def status_callback(msg):
    with position_lock:
        position[0] = msg.x
        position[1] = msg.y
        position[2] = msg.z

def move(pub, x, y, z, duration=DURATION):
    msg = SetJetMax()
    msg.x = float(x)
    msg.y = float(y)
    msg.z = float(z)
    msg.duration = float(duration)
    pub.publish(msg)

def prompt(stdscr, prompt_text):
    """Show a prompt and get text input from user."""
    stdscr.clear()
    stdscr.addstr(0, 0, prompt_text)
    stdscr.clrtoeol()
    stdscr.refresh()
    curses.curs_set(1)
    curses.echo()
    stdscr.nodelay(False)
    try:
        result = stdscr.getstr(1, 0, 30).decode('utf-8').strip()
    except Exception:
        result = ""
    curses.noecho()
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.clear()
    return result

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    load_positions()

    rospy.init_node('wasd_control', anonymous=True)
    pub = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)
    rospy.Subscriber('/jetmax/status', JetMaxState, status_callback)

    stdscr.addstr(0, 0, "Waiting for jetmax_control to connect...")
    stdscr.refresh()
    while pub.get_num_connections() == 0:
        time.sleep(0.1)

    move(pub, *HOME, duration=1.5)
    time.sleep(2)

    last_move_time = 0
    status_msg = ""

    while not rospy.is_shutdown():
        stdscr.clear()

        with position_lock:
            x, y, z = position[0], position[1], position[2]

        # Draw UI
        stdscr.addstr(0, 0,  "  JetMax WASD Controller", curses.A_BOLD)
        stdscr.addstr(1, 0,  " ─────────────────────────────────────")
        stdscr.addstr(2, 0,  f"  X: {x:>8.1f} mm   (A / D)")
        stdscr.addstr(3, 0,  f"  Y: {y:>8.1f} mm   (W / S)")
        stdscr.addstr(4, 0,  f"  Z: {z:>8.1f} mm   (R / F)")
        stdscr.addstr(5, 0,  " ─────────────────────────────────────")
        stdscr.addstr(6, 0,  "  W/S  Forward/Back   R/F  Up/Down")
        stdscr.addstr(7, 0,  "  A/D  Left/Right     SPACE  Home")
        stdscr.addstr(8, 0,  "  P  Save position    G  Go to saved")
        stdscr.addstr(9, 0,  "  L  List saved       Q  Quit")
        stdscr.addstr(10, 0, " ─────────────────────────────────────")

        # Show saved positions
        if saved_positions:
            stdscr.addstr(11, 0, "  Saved positions:")
            for i, p in enumerate(saved_positions):
                stdscr.addstr(12 + i, 0, f"  [{i}] {p['name']:12s}  x={p['x']:7.1f}  y={p['y']:7.1f}  z={p['z']:7.1f}")
        else:
            stdscr.addstr(11, 0, "  No saved positions yet — press P to save one")

        if status_msg:
            stdscr.addstr(12 + len(saved_positions), 0, f"  {status_msg}", curses.A_BOLD)

        key = stdscr.getch()

        now = time.time()
        if now - last_move_time < DURATION:
            stdscr.refresh()
            continue

        nx, ny, nz = x, y, z
        moved = False
        status_msg = ""

        if key == ord('w') or key == ord('W'):
            ny -= STEP;  moved = True
        elif key == ord('s') or key == ord('S'):
            ny += STEP;  moved = True
        elif key == ord('a') or key == ord('A'):
            nx -= STEP;  moved = True
        elif key == ord('d') or key == ord('D'):
            nx += STEP;  moved = True
        elif key == ord('r') or key == ord('R'):
            nz += STEP;  moved = True
        elif key == ord('f') or key == ord('F'):
            nz -= STEP;  moved = True
        elif key == ord(' '):
            nx, ny, nz = HOME;  moved = True
            status_msg = "Returning home..."

        elif key == ord('p') or key == ord('P'):
            name = prompt(stdscr, "  Save as (name): ")
            if name:
                saved_positions.append({'name': name, 'x': round(x, 1), 'y': round(y, 1), 'z': round(z, 1)})
                save_positions()
                status_msg = f"Saved [{len(saved_positions)-1}] {name} → ({x:.1f}, {y:.1f}, {z:.1f})"

        elif key == ord('g') or key == ord('G'):
            slot = prompt(stdscr, "  Go to slot #: ")
            if slot.isdigit() and int(slot) < len(saved_positions):
                p = saved_positions[int(slot)]
                move(pub, p['x'], p['y'], p['z'], duration=1.2)
                status_msg = f"Moving to [{slot}] {p['name']}"
                last_move_time = now
            else:
                status_msg = "Invalid slot number"

        elif key == ord('l') or key == ord('L'):
            status_msg = f"{len(saved_positions)} position(s) saved"

        elif key == ord('q') or key == ord('Q'):
            break

        if moved:
            move(pub, nx, ny, nz)
            last_move_time = now

        stdscr.refresh()

    move(pub, *HOME, duration=1.5)

curses.wrapper(main)
print("Controller closed. Arm returned home.")
print(f"Saved positions stored in: {SAVED_POSITIONS_FILE}")
