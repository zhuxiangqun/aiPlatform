"""Router/server _inject_http_request_context must route identity via actor_from_http."""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_TARGETS = [
    _ROOT / "api" / "routers" / "agents.py",
    _ROOT / "api" / "routers" / "engine_skills.py",
    _ROOT / "api" / "routers" / "traces_graphs.py",
    _ROOT / "api" / "routers" / "workspace_agents.py",
    _ROOT / "api" / "routers" / "workspace_skills.py",
    _ROOT / "server.py",
]


def _inject_body(src: str) -> str:
    assert "def _inject_http_request_context" in src
    return src.split("def _inject_http_request_context", 1)[1].split("\ndef ", 1)[0]


def test_inject_helpers_use_actor_from_http_not_raw_actor_headers():
    for path in _TARGETS:
        src = path.read_text(encoding="utf-8")
        fn = _inject_body(src)
        assert "actor_from_http" in fn or "_actor_from_http_dep" in fn, path.name
        assert not re.search(r'headers\.get\(["\']X-AIPLAT-ACTOR-ID', fn), path.name
        assert not re.search(r'headers\.get\(["\']X-AIPLAT-ACTOR-ROLE', fn), path.name
        assert not re.search(r'headers\.get\(["\']X-AIPLAT-TENANT-ID', fn), path.name


def test_workspace_agents_autosmoke_does_not_default_admin_from_raw_header():
    src = (_ROOT / "api" / "routers" / "workspace_agents.py").read_text(encoding="utf-8")
    assert 'headers.get("X-AIPLAT-ACTOR-ID", "admin")' not in src
    assert 'headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")' not in src


def test_packages_routers_do_not_read_raw_actor_headers():
    for rel in ("api/routers/packages_registry.py", "api/routers/workspace_packages.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "actor_from_http" in src, rel
        assert 'headers.get("X-AIPLAT-ACTOR-ID"' not in src, rel
        assert 'headers.get("X-AIPLAT-TENANT-ID"' not in src, rel
        assert 'headers.get("X-AIPLAT-ACTOR-ID", "admin")' not in src, rel
