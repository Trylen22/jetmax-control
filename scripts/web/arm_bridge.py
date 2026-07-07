"""ROS bridge for browser-based JetMax arm control."""
import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))
from paths import SAVED_POSITIONS_FILE, ensure_data_dir  # noqa: E402

import rospy  # noqa: E402
from jetmax_control.msg import SetJetMax, JetMax as JetMaxState  # noqa: E402

STEP = 10
DURATION = 0.3
HOME = (0, -160, 200)

_bridge = None
_bridge_lock = threading.Lock()


class ArmBridge:
    def __init__(self):
        if not rospy.core.is_initialized():
            rospy.init_node("web_arm_control", anonymous=True, disable_signals=True)
        self.pub = rospy.Publisher("/jetmax/command", SetJetMax, queue_size=1)
        self.position = list(HOME)
        self.pos_lock = threading.Lock()
        self.last_move = 0.0
        self.session_active = False
        rospy.Subscriber("/jetmax/status", JetMaxState, self._status_cb)

    def _status_cb(self, msg):
        with self.pos_lock:
            self.position[0] = msg.x
            self.position[1] = msg.y
            self.position[2] = msg.z

    def wait_for_arm(self, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.pub.get_num_connections() > 0:
                return True
            time.sleep(0.1)
        return False

    def get_state(self):
        with self.pos_lock:
            x, y, z = self.position[0], self.position[1], self.position[2]
        return {
            "session_active": self.session_active,
            "arm_connected": self.pub.get_num_connections() > 0,
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1),
        }

    def move(self, x, y, z, duration=DURATION):
        msg = SetJetMax()
        msg.x = float(x)
        msg.y = float(y)
        msg.z = float(z)
        msg.duration = float(duration)
        self.pub.publish(msg)

    def start_session(self):
        self.session_active = True
        connected = self.wait_for_arm()
        if connected:
            self.move(*HOME, duration=1.5)
            time.sleep(0.5)
        state = self.get_state()
        state["ok"] = True
        state["message"] = "connected" if connected else "waiting for jetmax_control"
        return state

    def stop_session(self):
        if self.session_active:
            self.move(*HOME, duration=1.5)
        self.session_active = False
        return {"ok": True}

    def jog(self, key):
        if not self.session_active:
            return {"ok": False, "reason": "session_inactive"}

        now = time.time()
        if now - self.last_move < DURATION:
            return {"ok": False, "reason": "rate_limited"}

        with self.pos_lock:
            x, y, z = self.position[0], self.position[1], self.position[2]

        key = str(key).lower()
        nx, ny, nz = x, y, z
        if key == "w":
            ny -= STEP
        elif key == "s":
            ny += STEP
        elif key == "a":
            nx -= STEP
        elif key == "d":
            nx += STEP
        elif key == "r":
            nz += STEP
        elif key == "f":
            nz -= STEP
        elif key in (" ", "space", "home"):
            nx, ny, nz = HOME
        else:
            return {"ok": False, "reason": "unknown_key"}

        self.move(nx, ny, nz)
        self.last_move = now
        return {"ok": True, "x": nx, "y": ny, "z": nz}

    def load_saved(self):
        ensure_data_dir()
        if SAVED_POSITIONS_FILE.exists():
            with open(SAVED_POSITIONS_FILE, "r") as f:
                return json.load(f)
        return []

    def save_position(self, name):
        name = str(name).strip()
        if not name:
            return {"ok": False, "reason": "empty_name"}
        with self.pos_lock:
            entry = {
                "name": name,
                "x": round(self.position[0], 1),
                "y": round(self.position[1], 1),
                "z": round(self.position[2], 1),
            }
        positions = self.load_saved()
        positions.append(entry)
        ensure_data_dir()
        with open(SAVED_POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)
        return {"ok": True, "index": len(positions) - 1, "position": entry}

    def go_saved(self, index):
        positions = self.load_saved()
        try:
            index = int(index)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_index"}
        if index < 0 or index >= len(positions):
            return {"ok": False, "reason": "bad_index"}
        pos = positions[index]
        self.move(pos["x"], pos["y"], pos["z"], duration=1.2)
        self.last_move = time.time()
        return {"ok": True, "position": pos}


def get_bridge():
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = ArmBridge()
        return _bridge
