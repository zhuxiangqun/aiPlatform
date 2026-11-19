"""N09 K64 — view_name runtime via DomainRouter.default_view_name()."""
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
    "aiPlat-core/core/harness/knowledge/domain_router.py",
    "aiPlat-core/core/harness/knowledge_pipeline/resolver.py",
    "aiPlat-core/core/apps/fde/service/k_wave_arbit.py",
]


def test_helper_stable():
    assert DomainRouter.default_view_name() == "default"
    assert DomainRouter.PLATFORM_DEFAULT_VIEW == "default"
    assert DomainRouter().default_view_name() == DomainRouter.default_view_name()


def test_targets_use_view_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "default_view_name()" in text or "PLATFORM_DEFAULT_VIEW" in text, rel
        assert 'view_name or "default"' not in text, rel
        assert 'get("view_name") or "default"' not in text, rel


def test_target_runtime_view_fallbacks_empty():
    """K64 targets: no remaining view_name \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_view_name" in ln or "PLATFORM_DEFAULT_VIEW" in ln:
                continue
            if "default_tenant" in ln or "PLATFORM_DEFAULT_TENANT" in ln:
                continue
            if "view" not in ln.lower():
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']view_name["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
