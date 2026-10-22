"""Sibling surfaces must not undo actor_from_http with raw header ORs."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[3]
_ACTOR_PATH = _ROOT / "api" / "deps" / "actor.py"
_TOOLS_PATH = _ROOT / "api" / "routers" / "tools.py"
_MCP_PATH = _ROOT / "api" / "routers" / "mcp_admin.py"


def _load_actor():
    spec = importlib.util.spec_from_file_location("aiplat_test_actor_siblings", _ACTOR_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_actor_from_http_ignores_spoofed_headers(monkeypatch):
    mod = _load_actor()
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    req = SimpleNamespace(
        headers={
            "X-AIPLAT-ACTOR-ID": "admin",
            "X-AIPLAT-ACTOR-ROLE": "admin",
            "X-AIPLAT-TENANT-ID": "victim",
        }
    )
    out = mod.actor_from_http(req, None)
    assert out == {"actor_id": None, "actor_role": None, "tenant_id": None}


def test_tools_inject_routes_identity_through_actor_from_http():
    src = _TOOLS_PATH.read_text(encoding="utf-8")
    fn = src.split("def _inject_http_request_context", 1)[1].split("\ndef ", 1)[0]
    assert "actor_from_http(http_request, payload)" in fn
    assert not re.search(r'headers\.get\(["\']X-AIPLAT-ACTOR-ID', fn)
    assert not re.search(r'headers\.get\(["\']X-AIPLAT-ACTOR-ROLE', fn)
    assert not re.search(r'headers\.get\(["\']X-AIPLAT-TENANT-ID', fn)


def test_mcp_admin_does_not_or_raw_actor_headers_after_gate():
    src = _MCP_PATH.read_text(encoding="utf-8")
    assert "headers.get(\"X-AIPLAT-ACTOR-ID\") or actor0" not in src
    assert "headers.get(\"X-AIPLAT-TENANT-ID\") or actor0" not in src
    assert "actor0.get(\"actor_id\") or \"anonymous\"" in src
