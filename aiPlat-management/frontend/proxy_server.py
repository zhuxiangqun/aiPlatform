#!/usr/bin/env python3
"""
Frontend proxy server with API routing.
Serves static frontend files and proxies API requests to backend services.
Supports SPA routing - all non-API, non-static routes return index.html.

Route discovery: on startup, fetches OpenAPI specs from all backends to build
a dynamic routing table. For prefixes that span multiple backends (e.g. /api/platform
is split between mgmt:8000 and platform:8003), 404 responses trigger automatic
fallback to the next target.
"""

import http.server
import json
import os
import sys
import urllib.request
import urllib.error

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)

CORE_DIRECT_URL = "http://localhost:8002"
INFRA_URL = "http://localhost:8001"
MGMT_URL = "http://localhost:8000"
PLATFORM_URL = "http://localhost:8003"
APP_URL = "http://localhost:8004"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

# ── Route discovery ────────────────────────────────────────────────────

_BACKEND_LABELS = {
    MGMT_URL: "mgmt:8000",
    CORE_DIRECT_URL: "core:8002",
    INFRA_URL: "infra:8001",
    PLATFORM_URL: "platform:8003",
    APP_URL: "app:8004",
}

# Prefixes that may exist on multiple backends — 404 on primary triggers fallback
_FALLBACK_PREFIXES: dict[str, list[str]] = {
    "/api/platform": [MGMT_URL, PLATFORM_URL],
}

def _discover_routes() -> dict[str, str]:
    """Fetch OpenAPI specs from all backends and build a routing table.
    Returns a dict of path_prefix → target_url.
    Falls back to static routes for backends that don't expose /openapi.json.
    """
    # Static base routes (always present, in priority order)
    static: dict[str, str] = {
        "/api/platform/apps/fde": PLATFORM_URL,  # platform-specific sub-paths → 8003
        "/api/platform/apps/ontology-editor": PLATFORM_URL,
        "/api/platform": MGMT_URL,  # base /apps list + documents/kb → management:8000
        "/api/core": CORE_DIRECT_URL,
        "/api/infra": INFRA_URL,
        "/api/dashboard": MGMT_URL,
        "/api/alerting": MGMT_URL,
        "/api/diagnostics": MGMT_URL,
        "/api/monitoring": MGMT_URL,
        "/api/app": APP_URL if APP_URL else MGMT_URL,
        "/api": MGMT_URL,  # catch-all for management
    }

    # For multi-backend prefixes: try to discover sub-routes from each backend
    for prefix, backends in _FALLBACK_PREFIXES.items():
        best = None
        for backend_url in backends:
            try:
                req = urllib.request.Request(f"{backend_url}/openapi.json")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    spec = json.loads(resp.read())
                paths = spec.get("paths", {})
                for api_path in paths:
                    # Skip wildcard/parameterized paths — they'd match too broadly
                    if "{" in api_path or api_path.endswith("{"):
                        continue
                    # Register sub-prefixes: /api/platform/apps, /api/platform/kb, etc.
                    parts = api_path.strip("/").split("/")
                    if len(parts) >= 3:
                        sub_prefix = "/" + "/".join(parts[:3])
                        # Skip sub-prefixes that fall under an existing static parent
                        # (e.g. /api/core/mcp should go to core:8002, not mgmt:8000)
                        parent = "/" + "/".join(parts[:2])
                        if parent in static and sub_prefix not in static:
                            # Stay with the parent's target (don't override with mgmt's route)
                            continue
                        if sub_prefix not in static:
                            static[sub_prefix] = backend_url
                            print(f"  [discovered] {sub_prefix:50s} → {_BACKEND_LABELS.get(backend_url, backend_url)}")
                # Register the broad prefix itself
                if best is None:
                    best = backend_url
            except Exception:
                continue
        if best and prefix not in static:
            static[prefix] = best

    return static

PROXY_ROUTES = _discover_routes()

# ── HTTP handler ───────────────────────────────────────────────────────

STATIC_EXTENSIONS = {'.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif',
                     '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.map', '.txt'}


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _get_target(self, path):
        """Find the backend target for a given path.
        Returns (target_url, is_precise_match) tuple.
        Precise matches (e.g. /api/platform/apps) don't trigger 404 fallback.
        """
        best_prefix = ""
        best_target = None
        for prefix, target in PROXY_ROUTES.items():
            if path.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
                best_target = target
        if best_target is None:
            return None, False
        # Precise = matched a discovered sub-prefix (≥3 segments), not a broad catch-all
        is_precise = best_prefix.count("/") >= 3
        return best_target, is_precise

    def _proxy_fallback_targets(self, path, primary_target):
        """If primary returns 404, return list of fallback backends to try."""
        for prefix, backends in _FALLBACK_PREFIXES.items():
            if path.startswith(prefix):
                # Remove primary from list, return remaining
                rest = [b for b in backends if b != primary_target]
                return rest
        return []

    def _do_proxy_request(self, target, method):
        """Execute a single proxy request. Returns (status, headers, body)."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            hop_by_hop = {"host","content-length","connection","keep-alive",
                          "proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade"}
            headers = {}
            for k, v in self.headers.items():
                if k.lower() in hop_by_hop:
                    continue
                headers[k] = v
            if body and "Content-Type" not in headers:
                headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
            req = urllib.request.Request(
                f"{target}{self.path}", data=body, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except Exception as e:
            return 502, {"Content-Type": "application/json"}, json.dumps({"error": str(e)}).encode()

    def _send_response(self, status, headers, body):
        self.send_response(status)
        ct = headers.get("Content-Type", "application/octet-stream")
        self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*")
        cd = headers.get("Content-Disposition", "")
        if cd:
            self.send_header("Content-Disposition", cd)
        cl = headers.get("Content-Length", "")
        if cl:
            self.send_header("Content-Length", cl)
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, method="GET"):
        target, is_precise = self._get_target(self.path)
        if target is None:
            self.send_error(404)
            return

        status, headers, body = self._do_proxy_request(target, method)

        # 404 fallback: try other backends for multi-backend prefixes
        if status == 404 and not is_precise:
            fallbacks = self._proxy_fallback_targets(self.path, target)
            for fb_target in fallbacks:
                fb_status, fb_headers, fb_body = self._do_proxy_request(fb_target, method)
                if fb_status != 404:
                    status, headers, body = fb_status, fb_headers, fb_body
                    break

        self._send_response(status, headers, body)

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
            sw_unregister = b"<script>navigator.serviceWorker?.getRegistrations().then(r=>r.forEach(x=>x.unregister()))</script>"
            content = content.replace(b"</head>", sw_unregister + b"</head>", 1)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "index.html not found")

    def _serve_static(self, path):
        filepath = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not filepath.startswith(os.path.normpath(STATIC_DIR)):
            self.send_error(403)
            return
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            ext = os.path.splitext(filepath)[1].lower()
            ctype = {
                ".js": "application/javascript", ".css": "text/css",
                ".html": "text/html", ".json": "application/json",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".svg": "image/svg+xml",
                ".woff": "font/woff", ".woff2": "font/woff2", ".ico": "image/x-icon",
            }.get(ext, "application/octet-stream")
            self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype.startswith("text/") or ctype.startswith("application/javascript") else ctype)
            self.send_header("Content-Length", str(len(content)))
            if ext in (".js", ".css", ".woff", ".woff2"):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            elif ext == ".html":
                self.send_header("Cache-Control", "no-cache")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def do_GET(self):
        target, _ = self._get_target(self.path)
        if target:
            self._proxy("GET")
        elif self._is_static_asset(self.path):
            self._serve_static(self.path)
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
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), ProxyHandler) as httpd:
        print(f"Frontend proxy running on http://0.0.0.0:{port}")
        print(f"Serving static files from: {STATIC_DIR}")
        print(f"Proxy routes: {list(PROXY_ROUTES.keys())}")
        httpd.serve_forever()
