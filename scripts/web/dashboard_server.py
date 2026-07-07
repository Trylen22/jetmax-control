#!/usr/bin/env python3
"""
dashboard_server.py — Serve the JetMax Control Deck (static HTML dashboard).

Opens on port 8888 by default. Open in browser:
  http://100.65.198.107:8888/

RUN:
  python3 ~/jetmax-control/scripts/web/dashboard_server.py
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8888
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ASSETS_DIR = os.path.join(REPO_ROOT, 'assets')


class DashboardHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split('?', 1)[0].split('#', 1)[0]
        if path in ('/', '/index.html', '/dashboard.html'):
            path = '/dashboard.html'
        local = path.lstrip('/')
        return os.path.join(ASSETS_DIR, local)

    def log_message(self, fmt, *args):
        sys.stdout.write("[dashboard] %s - %s\n" % (self.address_string(), fmt % args))


def main():
    os.chdir(ASSETS_DIR)
    server = HTTPServer(('0.0.0.0', PORT), DashboardHandler)
    host = os.environ.get('JETMAX_HOST', '100.65.198.107')
    print("JetMax Control Deck")
    print("===================")
    print("  Local   http://127.0.0.1:%d/" % PORT)
    print("  Remote  http://%s:%d/" % (host, PORT))
    print("  Camera  http://%s:8080/stream?topic=/usb_cam/image_rect_color" % host)
    print("\nCtrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        print("Dashboard stopped.")


if __name__ == '__main__':
    main()
