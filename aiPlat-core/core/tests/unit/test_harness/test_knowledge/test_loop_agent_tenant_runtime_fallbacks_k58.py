"""N09 K58 — loop/agent tenant+session runtime ``"default"`` via DomainRouter helpers."""
from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


from core.harness.knowledge.domain_router import DomainRouter

TARGETS = [
    "aiPlat-core/core/harness/execution/loop/_facade.py",
    "aiPlat-core/core/apps/agents/operator_agent.py",
    "aiPlat-core/core/harness/integration/agent.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"
    assert DomainRouter.default_session() == "default"


def test_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_tenant()" in text or "DomainRouter.default_session()" in text, rel
        assert 'get("tenant_id", "default")' not in text, rel
        assert 'get("session_id", "default")' not in text, rel
        assert 'tenant_id or "default"' not in text, rel


def test_target_runtime_tenant_session_fallbacks_empty():
    """K58 targets: no remaining tenant/session \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_tenant" in ln or "default_session" in ln or "PLATFORM_DEFAULT" in ln:
                continue
            if "tenant" not in ln.lower() and "session" not in ln.lower():
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\'](?:tenant_id|session_id)["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
