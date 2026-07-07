#!/usr/bin/env python3
"""
dashboard_server.py — JetMax Control Deck with live arm API.

Serves the dashboard on port 8888 and exposes REST endpoints for
browser-based WASD arm control (requires ROS — use ./run.sh dashboard).

  http://100.65.198.107:8888/
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8888
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")

try:
    from arm_bridge import get_bridge
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from arm_bridge import get_bridge


class ControlDeckHandler(SimpleHTTPRequestHandler):
    def _json_response(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def _handle_api(self, method):
        path = self.path.split("?", 1)[0]

        try:
            bridge = get_bridge()
        except Exception as exc:
            return self._json_response(500, {"ok": False, "error": str(exc)})

        if method == "GET":
            if path == "/api/health":
                state = bridge.get_state()
                state["ok"] = True
                return self._json_response(200, state)
            if path == "/api/position":
                return self._json_response(200, bridge.get_state())
            if path == "/api/positions":
                return self._json_response(200, {"ok": True, "positions": bridge.load_saved()})

        if method == "POST":
            data = self._read_json()
            if path == "/api/session/start":
                return self._json_response(200, bridge.start_session())
            if path == "/api/session/stop":
                return self._json_response(200, bridge.stop_session())
            if path == "/api/jog":
                return self._json_response(200, bridge.jog(data.get("key", "")))
            if path == "/api/positions/save":
                return self._json_response(200, bridge.save_position(data.get("name", "")))
            if path == "/api/positions/go":
                return self._json_response(200, bridge.go_saved(data.get("index", -1)))

        return self._json_response(404, {"ok": False, "error": "not_found"})

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", "/index.html", "/dashboard.html"):
            path = "/dashboard.html"
        local = path.lstrip("/")
        return os.path.join(ASSETS_DIR, local)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._handle_api("GET")
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._handle_api("POST")
        self.send_error(404)

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/position"):
            return
        sys.stdout.write("[deck] %s - %s\n" % (self.address_string(), fmt % args))


def main():
    os.chdir(ASSETS_DIR)
    host = os.environ.get("JETMAX_HOST", "100.65.198.107")
    print("JetMax Control Deck + Arm API")
    print("==============================")
    print("  Dashboard  http://127.0.0.1:%d/" % PORT)
    print("  Remote     http://%s:%d/" % (host, PORT))
    print("  Camera     http://%s:8080/stream?topic=/usb_cam/image_rect_color" % host)
    print("\nArm Control module runs WASD in the browser.")
    print("Ctrl+C to stop.\n")
    server = HTTPServer(("0.0.0.0", PORT), ControlDeckHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            get_bridge().stop_session()
        except Exception:
            pass
        server.shutdown()
        print("Dashboard stopped.")


if __name__ == "__main__":
    main()
