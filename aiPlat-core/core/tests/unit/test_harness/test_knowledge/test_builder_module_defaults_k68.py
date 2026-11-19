"""N09 K68 — builder module_id via DomainRouter.default_module_id()."""
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
    "aiPlat-platform/builder/builder_l2l5_mixin.py",
    "aiPlat-platform/builder/builder_project_service.py",
    "aiPlat-platform/builder/schema_migration.py",
]


def test_helper_stable():
    assert DomainRouter.default_module_id() == "default"
    assert DomainRouter.PLATFORM_DEFAULT_MODULE == "default"


def test_targets_use_module_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "default_module_id()" in text or "PLATFORM_DEFAULT_MODULE" in text, rel


def test_target_builder_module_defaults_empty():
    """K68 targets: no remaining module_id \"default\" literals."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_module_id" in ln or "PLATFORM_DEFAULT_MODULE" in ln:
                continue
            if "module" not in ln.lower():
                continue
            if '== "default"' in ln or '!= "default"' in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'module_id: str = "default"' in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'module_id["\']?\s*[:=].*["\']default["\']', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif '_module_root(project_id, "default")' in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
