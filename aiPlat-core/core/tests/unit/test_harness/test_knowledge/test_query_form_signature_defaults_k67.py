"""N09 K67 — Query/Form/signature defaults via DomainRouter helpers."""
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
    "aiPlat-platform/apps/workbench/api/kanban.py",
    "aiPlat-platform/apps/fde/api/extraction_routes.py",
    "aiPlat-platform/apps/fde/api/fde.py",
    "aiPlat-platform/apps/fde/api/action_routes.py",
    "aiPlat-platform/apps/fde/api/rapid_insight.py",
    "aiPlat-platform/api/routers/conversations.py",
    "aiPlat-core/core/server.py",
    "aiPlat-platform/apps/value/api/safety.py",
    "aiPlat-platform/apps/org/api/routes.py",
    "aiPlat-core/core/api/routers/diagnostics_capability.py",
    "aiPlat-core/core/harness/memory/manager.py",
    "aiPlat-core/core/api/routers/wiki.py",
    "aiPlat-core/core/api/routers/wiki_scenes.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"
    assert DomainRouter.default_collection() == "default"
    assert DomainRouter.default_profile() == "default"
    assert DomainRouter.default_session() == "default"
    assert DomainRouter.default_graph_domain() == "default"


def test_targets_use_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_" in text, rel


def test_target_query_form_signature_defaults_empty():
    """K67 targets: no Query/Form/signature \"default\" leftovers for isolation ids."""
    hits = []
    pat = re.compile(
        r'Query\(["\']default["\']\)|Form\(["\']default["\']\)|'
        r'collection:\s*str\s*=\s*["\']default["\']|'
        r'namespace:\s*str\s*=\s*["\']default["\']|'
        r'"collection_id":\s*["\']default["\']'
    )
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_tenant" in ln or "default_collection" in ln or "default_profile" in ln:
                continue
            if "default_session" in ln or "default_graph_domain" in ln:
                continue
            if pat.search(ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
