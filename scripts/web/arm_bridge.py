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

# Vision pick — closed-loop centering then grab
APPROACH_Z = 180.0
PICK_Z = 100.0  # grab / release height
TOOL_OFFSET_X = -37.0  # camera → sucker (applied after centering)
TOOL_OFFSET_Y = 5.0
CENTER_TOL_MM = 4.0    # stop when |offset| under this
CENTER_GAIN = 0.55     # fraction of offset to move each step (avoids overshoot)
CENTER_MAX_ITERS = 12
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
        self.last_pick = None  # {"x", "y"} from last successful vision pick
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
        state = {
            "session_active": self.session_active,
            "arm_connected": self.pub.get_num_connections() > 0,
            "busy": self.busy,
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1),
            "last_pick": None,
        }
        if self.last_pick:
            state["last_pick"] = {
                "x": round(self.last_pick["x"], 1),
                "y": round(self.last_pick["y"], 1),
            }
        return state

    def _run_pick_place(self, from_x, from_y, to_x, to_y):
        """Grab at (from_x, from_y) and drop at (to_x, to_y)."""
        # Approach source
        self.move(from_x, from_y, APPROACH_Z, duration=1.2)
        time.sleep(1.4)
        self.move(from_x, from_y, PICK_Z, duration=1.0)
        time.sleep(1.2)
        self.suction(True)
        time.sleep(0.4)
        self.move(from_x, from_y, APPROACH_Z, duration=1.0)
        time.sleep(1.2)
        # Carry to destination
        self.move(to_x, to_y, APPROACH_Z, duration=1.5)
        time.sleep(1.7)
        self.move(to_x, to_y, PICK_Z, duration=1.0)
        time.sleep(1.2)
        self.suction(False)
        time.sleep(0.3)
        self.move(to_x, to_y, APPROACH_Z, duration=1.0)
        time.sleep(1.1)
        self.last_move = time.time()

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

    def _center_on_target(self, timeout=10.0):
        """
        Closed-loop visual servo: nudge XY until the blob is near image center.
        Does NOT apply tool offset — that happens once after centering.
        Returns (ok, info_dict).
        """
        deadline = time.time() + timeout
        last_dx = last_dy = None
        iters = 0

        # Work at approach height so the camera sees the block clearly
        with self.pos_lock:
            x, y = self.position[0], self.position[1]
        self.move(x, y, APPROACH_Z, duration=1.0)
        time.sleep(1.1)

        while iters < CENTER_MAX_ITERS and time.time() < deadline:
            det = self._wait_for_detection(timeout=1.5)
            if not det or not det.get("detected"):
                if last_dx is None:
                    err = (det or {}).get("_error")
                    return False, {
                        "reason": "no_target",
                        "hint": (
                            "Vision stream unreachable (%s)." % err
                            if err else
                            "No target — keep block in view with Vision overlay on."
                        ),
                    }
                # Lost briefly after we had a lock — retry
                time.sleep(0.2)
                continue

            dx = float(det.get("arm_dx_mm", 0))
            dy = float(det.get("arm_dy_mm", 0))
            last_dx, last_dy = dx, dy
            iters += 1

            sys.stdout.write(
                "[deck] center iter %d: offset dx=%.1f dy=%.1f mm\n" % (iters, dx, dy)
            )
            sys.stdout.flush()

            if abs(dx) <= CENTER_TOL_MM and abs(dy) <= CENTER_TOL_MM:
                with self.pos_lock:
                    cx, cy = self.position[0], self.position[1]
                return True, {
                    "x": cx,
                    "y": cy,
                    "dx_mm": dx,
                    "dy_mm": dy,
                    "iters": iters,
                    "area": det.get("area"),
                }

            # Partial step toward the target (gain < 1 damps overshoot)
            with self.pos_lock:
                x, y = self.position[0], self.position[1]
            nx = x + dx * CENTER_GAIN
            ny = y + dy * CENTER_GAIN
            self.move(nx, ny, APPROACH_Z, duration=0.55)
            time.sleep(0.7)

        return False, {
            "reason": "center_timeout",
            "hint": "Could not center on target (last offset dx=%s dy=%s)."
            % (last_dx, last_dy),
            "dx_mm": last_dx,
            "dy_mm": last_dy,
            "iters": iters,
        }

    def pick_target(self):
        """
        Vision pick with closed-loop centering:
          servo until blob is centered → apply tool offset → grab → drop at HOME.
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
            sys.stdout.write("[deck] pick_target: centering on target…\n")
            sys.stdout.flush()
            ok, info = self._center_on_target(timeout=12.0)
            if not ok:
                return {
                    "ok": False,
                    "reason": info.get("reason", "no_target"),
                    "hint": info.get("hint"),
                }

            # Camera is now over the block — shift to sucker frame once
            pick_x = info["x"] + TOOL_OFFSET_X
            pick_y = info["y"] + TOOL_OFFSET_Y
            self.last_pick = {"x": pick_x, "y": pick_y}

            hx, hy, hz = HOME
            sys.stdout.write(
                "[deck] pick_target: centered → tool (%.1f, %.1f) → home (%.1f, %.1f) [%d iters]\n"
                % (pick_x, pick_y, hx, hy, info.get("iters", 0))
            )
            sys.stdout.flush()
            self._run_pick_place(pick_x, pick_y, hx, hy)
            self.move(hx, hy, hz, duration=1.0)
            time.sleep(1.1)

            state = self.get_state()
            state["ok"] = True
            state["picked"] = {
                "pick_x": round(pick_x, 1),
                "pick_y": round(pick_y, 1),
                "dx_mm": info.get("dx_mm"),
                "dy_mm": info.get("dy_mm"),
                "iters": info.get("iters"),
                "area": info.get("area"),
            }
            state["message"] = "centered, picked, and dropped at home"
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

    def return_target(self):
        """
        Grab the block from HOME (where Pick dropped it) and place it
        back at the last vision-pick coordinates.
        """
        if not self.session_active:
            return {"ok": False, "reason": "session_inactive"}
        if not self.wait_for_arm(timeout=2.0):
            return {"ok": False, "reason": "arm_disconnected"}
        if not self.last_pick:
            return {
                "ok": False,
                "reason": "no_last_pick",
                "hint": "Run Pick → home first so the origin is remembered.",
            }

        with self.busy_lock:
            if self.busy:
                return {"ok": False, "reason": "busy"}
            self.busy = True

        try:
            hx, hy, hz = HOME
            tx = float(self.last_pick["x"])
            ty = float(self.last_pick["y"])
            sys.stdout.write(
                "[deck] return_target: home (%.1f, %.1f) → origin (%.1f, %.1f)\n"
                % (hx, hy, tx, ty)
            )
            sys.stdout.flush()
            self._run_pick_place(hx, hy, tx, ty)
            # Leave arm above the returned spot, then park at home
            self.move(hx, hy, hz, duration=1.5)
            time.sleep(1.6)

            state = self.get_state()
            state["ok"] = True
            state["returned"] = {"x": round(tx, 1), "y": round(ty, 1)}
            state["message"] = "returned target to origin"
            return state
        except Exception as exc:
            try:
                self.suction(False)
            except Exception:
                pass
            return {"ok": False, "reason": "return_failed", "error": str(exc)}
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
