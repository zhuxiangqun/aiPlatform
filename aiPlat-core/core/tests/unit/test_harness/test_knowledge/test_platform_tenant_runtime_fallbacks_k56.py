"""N09 K56 — platform routes/kb/delivery tenant runtime ``or "default"`` via DomainRouter.default_tenant()."""
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
    "aiPlat-platform/api/rest/routes.py",
    "aiPlat-platform/api/routers/onboarding.py",
    "aiPlat-platform/api/routers/conversations.py",
    "aiPlat-platform/api/routers/approvals.py",
    "aiPlat-platform/kb/storage.py",
    "aiPlat-platform/kb/platform_query.py",
    "aiPlat-platform/delivery/kb_health.py",
    "aiPlat-platform/delivery/monthly_ops_report.py",
    "aiPlat-platform/delivery/l3_duty_desk.py",
    "aiPlat-platform/delivery/cost_report.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"


def test_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_tenant()" in text, rel
        assert 'tenant_id or "default"' not in text, rel
        assert '(tenant_id or "").strip() or "default"' not in text, rel


def test_target_runtime_tenant_fallbacks_empty():
    """K56 targets: no remaining tenant_id ... \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_tenant" in ln or "PLATFORM_DEFAULT_TENANT" in ln:
                continue
            if "collection_id" in ln or "session_id" in ln:
                continue
            if "tenant" not in ln.lower():
                continue
            # 仅抓运行时字面量回退，不把 get("tenant_id") or "" / None 误报为命中
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']tenant_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'strip() or "default"' in ln or "strip() or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
