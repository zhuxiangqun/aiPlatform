#!/usr/bin/env python3
"""ADR-09 ontology BOUNDARY C — thin optional-deploy health HTTP (stdlib only).

One-shot / local bind. Not a long-running compose service.
Does not start a second DomainRouter registry or control-plane split.
Env: AIPLAT_HOME, AIPLAT_ONTOLOGY_OPTIONAL_SPLIT, ADR09_ONTOLOGY_HEALTH_PORT (default 18767).
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
        ont_dir = os.path.join(home, "ontologies") if home else ""
        body = json.dumps(
            {
                "ok": True,
                "product": "ontology",
                "aiplat_home": home,
                "ontologies_dir": ont_dir,
                "ontologies_dir_exists": bool(ont_dir) and os.path.isdir(ont_dir),
                "optional_split": os.environ.get("AIPLAT_ONTOLOGY_OPTIONAL_SPLIT", "0"),
                "registry": "$AIPLAT_HOME/ontologies/registry.json",
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
    port = int(os.environ.get("ADR09_ONTOLOGY_HEALTH_PORT", "18767"))
    host = os.environ.get("ADR09_ONTOLOGY_HEALTH_HOST", "127.0.0.1")
    httpd = HTTPServer((host, port), _Handler)
    print(f"ontology optional health listening on http://{host}:{port}/health", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
