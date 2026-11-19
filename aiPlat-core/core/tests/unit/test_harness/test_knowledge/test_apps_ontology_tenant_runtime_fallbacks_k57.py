"""N09 K57 — apps + ontology_engine tenant runtime ``or "default"`` via DomainRouter.default_tenant()."""
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
    "aiPlat-core/core/harness/ontology_engine/ontology_branch.py",
    "aiPlat-core/core/harness/ontology_engine/state_history.py",
    "aiPlat-core/core/harness/evaluation/code_review_gold.py",
    "aiPlat-platform/apps/org/api/routes.py",
    "aiPlat-platform/apps/value/api/safety.py",
    "aiPlat-platform/apps/fde/api/rapid_insight.py",
    "aiPlat-platform/apps/prompt/api/prompt_templates.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"


def test_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_tenant()" in text, rel
        assert 'tenant_id or "default"' not in text, rel
        assert '(tenant_id or "default").strip() or "default"' not in text, rel
        assert 'body.get("tenant_id", "default")' not in text, rel
        assert 'session.get("tenant_id", "default")' not in text, rel


def test_target_runtime_tenant_fallbacks_empty():
    """K57 targets: no remaining tenant_id ... \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_tenant" in ln or "PLATFORM_DEFAULT_TENANT" in ln:
                continue
            if "collection_id" in ln or "session_id" in ln:
                continue
            if "tenant" not in ln.lower() and 'or "default"' not in ln and "or 'default'" not in ln:
                # still catch bare tid == "default" / != "default" in ontology_branch
                if '== "default"' in ln or '!= "default"' in ln:
                    hits.append(f"{rel}:{i}:{ln.strip()}")
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']tenant_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif '== "default"' in ln or '!= "default"' in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
