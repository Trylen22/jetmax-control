"""ROS bridge for browser-based JetMax arm control."""
import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))
from paths import SAVED_POSITIONS_FILE, ensure_data_dir  # noqa: E402

import rospy  # noqa: E402
from jetmax_control.msg import SetJetMax, JetMax as JetMaxState  # noqa: E402
from std_msgs.msg import Bool  # noqa: E402

STEP = 10
DURATION = 0.3
HOME = (0.0, -160.0, 200.0)

# Vision pick — same tuning as belt_vision.py (watch from current XY)
APPROACH_Z = 180.0
PICK_Z = 125.0
TOOL_OFFSET_X = -37.0
TOOL_OFFSET_Y = 5.0
DETECTION_URL = "http://127.0.0.1:8081/detection.json"

_bridge = None
_bridge_lock = threading.Lock()


class ArmBridge:
    def __init__(self):
        if not rospy.core.is_initialized():
            rospy.init_node("web_arm_control", anonymous=True, disable_signals=True)
        self.pub = rospy.Publisher("/jetmax/command", SetJetMax, queue_size=1)
        self.sucker_pub = rospy.Publisher(
            "/jetmax/end_effector/sucker/command", Bool, queue_size=1
        )
        self.position = list(HOME)
        self.pos_lock = threading.Lock()
        self.last_move = 0.0
        self.session_active = False
        self.busy = False
        self.busy_lock = threading.Lock()
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
            "busy": self.busy,
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
        with self.pos_lock:
            self.position[0] = float(x)
            self.position[1] = float(y)
            self.position[2] = float(z)

    def suction(self, on):
        self.sucker_pub.publish(Bool(data=bool(on)))
        time.sleep(0.35)

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
            try:
                self.suction(False)
            except Exception:
                pass
            self.move(*HOME, duration=1.5)
        self.session_active = False
        return {"ok": True}

    def jog(self, key):
        if not self.session_active:
            return {"ok": False, "reason": "session_inactive"}
        if self.busy:
            return {"ok": False, "reason": "busy"}

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

    def _fetch_detection(self):
        try:
            req = Request(DETECTION_URL, headers={"Cache-Control": "no-cache"})
            with urlopen(req, timeout=0.8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {"_error": str(exc)}

    def _wait_for_detection(self, timeout=4.0):
        """Poll vision-stream until a target is held, or timeout."""
        deadline = time.time() + timeout
        last = None
        last_err = None
        while time.time() < deadline:
            d = self._fetch_detection()
            if d and d.get("_error"):
                last_err = d["_error"]
            else:
                last = d
                if d and d.get("detected"):
                    return d
            time.sleep(0.15)
        if last is None and last_err:
            return {"detected": False, "_error": last_err}
        return last

    def pick_target(self):
        """
        Vision pick from current XY:
          detect green/cyan → approach → grab → lift → drop at HOME → release.
        """
        if not self.session_active:
            return {"ok": False, "reason": "session_inactive"}
        if not self.wait_for_arm(timeout=2.0):
            return {"ok": False, "reason": "arm_disconnected"}

        with self.busy_lock:
            if self.busy:
                return {"ok": False, "reason": "busy"}
            self.busy = True

        try:
            sys.stdout.write("[deck] pick_target: waiting for detection…\n")
            sys.stdout.flush()
            det = self._wait_for_detection(timeout=4.0)
            if not det or not det.get("detected"):
                err = (det or {}).get("_error")
                return {
                    "ok": False,
                    "reason": "no_target",
                    "hint": (
                        "Vision stream unreachable (%s). Is jetmax-vision running?" % err
                        if err else
                        "No target — keep block in view with Vision overlay on."
                    ),
                }

            dx = float(det.get("arm_dx_mm", 0))
            dy = float(det.get("arm_dy_mm", 0))
            with self.pos_lock:
                wx, wy, wz = self.position[0], self.position[1], self.position[2]

            pick_x = wx + dx + TOOL_OFFSET_X
            pick_y = wy + dy + TOOL_OFFSET_Y

            # Approach above target
            self.move(pick_x, pick_y, APPROACH_Z, duration=1.2)
            time.sleep(1.4)
            # Descend and grab
            self.move(pick_x, pick_y, PICK_Z, duration=1.0)
            time.sleep(1.2)
            self.suction(True)
            time.sleep(0.4)
            # Lift
            self.move(pick_x, pick_y, APPROACH_Z, duration=1.0)
            time.sleep(1.2)
            # Carry to home and drop
            hx, hy, hz = HOME
            self.move(hx, hy, APPROACH_Z, duration=1.5)
            time.sleep(1.7)
            self.move(hx, hy, PICK_Z, duration=1.0)
            time.sleep(1.2)
            self.suction(False)
            time.sleep(0.3)
            self.move(hx, hy, hz, duration=1.0)
            time.sleep(1.1)
            self.last_move = time.time()

            state = self.get_state()
            state["ok"] = True
            state["picked"] = {
                "pick_x": round(pick_x, 1),
                "pick_y": round(pick_y, 1),
                "dx_mm": dx,
                "dy_mm": dy,
                "area": det.get("area"),
            }
            state["message"] = "picked and dropped at home"
            return state
        except Exception as exc:
            try:
                self.suction(False)
            except Exception:
                pass
            return {"ok": False, "reason": "pick_failed", "error": str(exc)}
        finally:
            with self.busy_lock:
                self.busy = False

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
