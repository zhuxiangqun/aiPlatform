"""Remote Core profile — registry + allowlisted proxy SSRF/route guards."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import pytest


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_REMOTE_CORE_ALLOW_PRIVATE", "1")
    return home


def test_create_remote_and_resolve_no_local_paths(isolated_home):
    from core.harness.named_workspace.registry import create_remote_workspace
    from core.harness.named_workspace.resolve import resolve_named_workspace

    entry = create_remote_workspace(
        "remote_a",
        label="Remote A",
        base_url="http://127.0.0.1:18090",
    )
    assert entry["kind"] == "remote"
    ctx = resolve_named_workspace("remote_a", method="GET")
    assert ctx.is_remote is True
    assert ctx.agents_dir == ""
    assert ctx.eval_results_dir == ""
    assert ctx.base_url.startswith("http://127.0.0.1")


def test_remote_ssrf_blocked_without_allow(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.delenv("AIPLAT_REMOTE_CORE_ALLOW_PRIVATE", raising=False)

    from core.harness.named_workspace.registry import create_remote_workspace

    with pytest.raises(ValueError, match="ssrf_blocked"):
        create_remote_workspace(
            "bad",
            base_url="http://127.0.0.1:9",
        )


def test_route_allowlist():
    from core.harness.named_workspace.remote_proxy import is_route_allowlisted

    assert is_route_allowlisted("GET", "/core/evaluation/sets")
    assert is_route_allowlisted("POST", "/core/evaluation/exam")
    assert not is_route_allowlisted("GET", "/core/admin/secrets")
    assert not is_route_allowlisted("DELETE", "/core/evaluation/sets")
    # Tightening
    assert not is_route_allowlisted(
        "GET",
        "/core/evaluation/sets",
        allowed_routes=["GET:/core/workspace"],
    )
    assert is_route_allowlisted(
        "GET",
        "/core/evaluation/sets",
        allowed_routes=["GET:/core/evaluation"],
    )


class _RemoteCoreHandler(BaseHTTPRequestHandler):
    last_headers = {}

    def do_GET(self):  # noqa: N802
        _RemoteCoreHandler.last_headers = {k.lower(): v for k, v in self.headers.items()}
        body = json.dumps(
            {"ok": True, "items": [{"id": "agent_x"}], "via": "mock_remote"}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        return


@pytest.fixture()
def mock_remote_core():
    server = HTTPServer(("127.0.0.1", 0), _RemoteCoreHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_proxy_forwards_allowlisted_and_strips_workspace_header(
    isolated_home, mock_remote_core, monkeypatch
):
    from core.harness.named_workspace.registry import create_remote_workspace
    from core.harness.named_workspace.remote_proxy import proxy_request

    create_remote_workspace("r1", base_url=mock_remote_core)
    _RemoteCoreHandler.last_headers = {}
    out = proxy_request(
        profile_id="r1",
        base_url=mock_remote_core,
        method="GET",
        path="/core/workspace/agents",
        body=b"",
        tenant_id="t1",
        actor_id="a1",
    )
    assert out["ok"] is True
    assert out["stripped_workspace_header"] is True
    data = json.loads(out["body"].decode("utf-8"))
    assert data.get("via") == "mock_remote"
    # Authorization / workspace header must not appear unless we set auth_secret_env
    assert "x-aiplat-workspace-id" not in _RemoteCoreHandler.last_headers


def test_proxy_rejects_non_allowlisted(isolated_home, mock_remote_core):
    from core.harness.named_workspace.remote_proxy import RemoteProxyError, proxy_request

    with pytest.raises(RemoteProxyError) as ei:
        proxy_request(
            profile_id="r1",
            base_url=mock_remote_core,
            method="GET",
            path="/core/admin/secrets",
        )
    assert ei.value.code == "remote_route_denied"


def test_paths_refuse_remote_active_context(isolated_home):
    from core.harness.named_workspace.registry import create_remote_workspace
    from core.harness.named_workspace.resolve import (
        resolve_named_workspace,
        set_active_named_workspace,
        reset_active_named_workspace,
    )
    from core.utils.paths import get_agents_dir

    create_remote_workspace("r2", base_url="http://127.0.0.1:18111")
    ctx = resolve_named_workspace("r2", method="GET")
    token = set_active_named_workspace(ctx)
    try:
        with pytest.raises(RuntimeError, match="workspace-proxy"):
            get_agents_dir()
    finally:
        reset_active_named_workspace(token)


def test_require_local_disk_rejects_remote(isolated_home):
    from fastapi import HTTPException

    from core.harness.named_workspace.http_bind import require_local_disk
    from core.harness.named_workspace.registry import create_remote_workspace
    from core.harness.named_workspace.resolve import resolve_named_workspace

    create_remote_workspace("r3", base_url="http://127.0.0.1:18112")
    ctx = resolve_named_workspace("r3", method="GET")
    with pytest.raises(HTTPException) as ei:
        require_local_disk(ctx)
    assert ei.value.status_code == 400
    assert ei.value.detail["error"] == "remote_local_disk_forbidden"
