"""N09 K66 — profile / AIPLAT_DEFAULT_TENANT runtime via DomainRouter helpers."""
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
    "aiPlat-core/core/harness/kernel/profile.py",
    "aiPlat-core/core/harness/scheduler/cron_loader.py",
    "aiPlat-core/core/harness/execution/loop/inference.py",
    "aiPlat-core/core/api/routers/kanban.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-core/core/apps/eval/service/judge_v1.py",
    "aiPlat-platform/tenants/manager.py",
]


def test_helper_stable():
    assert DomainRouter.default_profile() == "default"
    assert DomainRouter.default_tenant() == "default"
    assert DomainRouter.default_session() == "default"


def test_targets_use_profile_tenant_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert (
            "default_profile()" in text
            or "default_tenant()" in text
            or "default_session()" in text
        ), rel


def test_target_runtime_profile_tenant_fallbacks_empty():
    """K66 targets: no remaining profile/tenant \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_profile" in ln or "default_tenant" in ln or "default_session" in ln:
                continue
            if "PLATFORM_DEFAULT" in ln:
                continue
            low = ln.lower()
            if "profile" not in low and "tenant" not in low and "namespace" not in low:
                continue
            if 'AIPLAT_DEFAULT_TENANT", "default"' in ln or "AIPLAT_DEFAULT_TENANT', 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'Query("default")' in ln or "Query('default')" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'name: str = "default"' in ln or "name: str = 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'ProfileConfig(name="default"' in ln or "ProfileConfig(name='default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']profile["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'else "default"' in ln or "else 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif ', "default")' in ln and "profile" in low:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
