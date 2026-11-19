"""N09 K59 — session runtime ``or "default"`` via DomainRouter.default_session()."""
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
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-core/core/harness/execution/file_checkpoint.py",
    "aiPlat-core/core/harness/infrastructure/gates/approval_inbox.py",
    "aiPlat-core/core/harness/infrastructure/gates/approval_reviewer.py",
    "aiPlat-core/core/harness/infrastructure/gates/session_write_provenance.py",
    "aiPlat-core/core/services/execution_store/session_mixin.py",
    "aiPlat-platform/api/rest/routes.py",
    "aiPlat-platform/api/routers/execution_snapshots.py",
    "aiPlat-platform/apps/fde/api/fde.py",
    "aiPlat-core/core/harness/digital_human/consultant_personal.py",
]


def test_helper_stable():
    assert DomainRouter.default_session() == "default"
    assert DomainRouter.default_tenant() == "default"


def test_targets_use_session_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert (
            "DomainRouter.default_session()" in text
            or "DomainRouter.default_tenant()" in text
        ), rel
        assert 'session_id or "default"' not in text, rel
        assert 'get("session_id", "default")' not in text, rel


def test_target_runtime_session_fallbacks_empty():
    """K59 targets: no remaining session/tenant strip-or \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_session" in ln or "default_tenant" in ln or "PLATFORM_DEFAULT" in ln:
                continue
            if "session" not in ln.lower() and "tenant" not in ln.lower():
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']session_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'strip() or "default"' in ln or "strip() or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
