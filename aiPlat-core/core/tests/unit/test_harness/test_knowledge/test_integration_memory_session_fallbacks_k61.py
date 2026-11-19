"""N09 K61 — integration/server/memory/approvals session runtime via DomainRouter.default_session()."""
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
    "aiPlat-core/core/harness/integration/__init__.py",
    "aiPlat-core/core/harness/integration.py",
    "aiPlat-core/core/server.py",
    "aiPlat-core/core/harness/memory/manager.py",
    "aiPlat-core/core/harness/memory/profile_builder.py",
    "aiPlat-core/core/harness/knowledge/seci_engine.py",
    "aiPlat-platform/api/routers/approvals.py",
    "aiPlat-platform/api/routers/gateway.py",
]


def test_helper_stable():
    assert DomainRouter.default_session() == "default"


def test_targets_use_session_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_session()" in text, rel
        assert 'get("session_id", "default")' not in text, rel


def test_target_runtime_session_fallbacks_empty():
    """K61 targets: no remaining session_id \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_session" in ln or "PLATFORM_DEFAULT_SESSION" in ln:
                continue
            # namespace 默认不是 session_id 字段回退（如 MemoryManager cache key）
            if "namespace or" in ln or "namespace=" in ln:
                continue
            if "session_id" not in ln and "session" not in ln.lower():
                continue
            if re.search(r'get\(["\']session_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif "session_id" in ln and ('or "default"' in ln or "or 'default'" in ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
