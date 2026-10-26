#!/usr/bin/env python3
"""ADR-09 control-plane BOUNDARY C — thin optional-deploy health HTTP (stdlib only).

One-shot / local bind. Not a long-running compose service.
Does not invent a second Identity/PolicyGate.
Env: AIPLAT_HOME, AIPLAT_CONTROL_PLANE_OPTIONAL_SPLIT, ADR09_CONTROL_PLANE_HEALTH_PORT (default 18768).
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in ("/health", "/healthz"):
            self.send_response(404)
            self.end_headers()
            return
        home = os.environ.get("AIPLAT_HOME", "")
        body = json.dumps(
            {
                "ok": True,
                "product": "control-plane",
                "aiplat_home": home,
                "home_exists": bool(home) and os.path.isdir(home),
                "optional_split": os.environ.get("AIPLAT_CONTROL_PLANE_OPTIONAL_SPLIT", "0"),
                "identity_authority": "aiPlat",
                "policy_gate": "single",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    port = int(os.environ.get("ADR09_CONTROL_PLANE_HEALTH_PORT", "18768"))
    host = os.environ.get("ADR09_CONTROL_PLANE_HEALTH_HOST", "127.0.0.1")
    httpd = HTTPServer((host, port), _Handler)
    print(f"control-plane optional health listening on http://{host}:{port}/health", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
