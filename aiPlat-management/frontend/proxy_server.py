#!/usr/bin/env python3
"""
Frontend proxy server with API routing.
Serves static frontend files and proxies API requests to backend services.
Supports SPA routing - all non-API, non-static routes return index.html.
"""

import http.server
import json
import os
import sys
import urllib.request
import urllib.error

CORE_URL = "http://localhost:8002"
INFRA_URL = "http://localhost:8001"
MGMT_URL = "http://localhost:8000"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

PROXY_ROUTES = {
    "/api/core": CORE_URL,
    "/api/infra": INFRA_URL,
    "/api/dashboard": MGMT_URL,
    "/api/alerting": MGMT_URL,
    "/api/diagnostics": MGMT_URL,
    "/api/monitoring": MGMT_URL,
}

STATIC_EXTENSIONS = {'.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif',
                     '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.map', '.txt'}


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _get_target(self, path):
        for prefix, target in PROXY_ROUTES.items():
            if path.startswith(prefix):
                return target
        return None

    def _is_static_asset(self, path):
        for ext in STATIC_EXTENSIONS:
            if path.endswith(ext):
                return True
        return False

    def _serve_spa(self):
        index_path = os.path.join(STATIC_DIR, "index.html")
        try:
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "index.html not found")

    def _proxy(self, method="GET"):
        target = self._get_target(self.path)
        if target is None:
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            headers = {}
            if body:
                headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
            req = urllib.request.Request(
                f"{target}{self.path}",
                data=body,
                method=method,
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        if self._get_target(self.path):
            self._proxy("GET")
        elif self._is_static_asset(self.path):
            super().do_GET()
        else:
            self._serve_spa()

    def do_POST(self):
        self._proxy("POST")

    def do_PUT(self):
        self._proxy("PUT")

    def do_DELETE(self):
        self._proxy("DELETE")

    def do_PATCH(self):
        self._proxy("PATCH")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    with http.server.HTTPServer(("0.0.0.0", port), ProxyHandler) as httpd:
        print(f"Frontend proxy running on http://0.0.0.0:{port}")
        print(f"Serving static files from: {STATIC_DIR}")
        print(f"Proxy routes: {list(PROXY_ROUTES.keys())}")
        httpd.serve_forever()