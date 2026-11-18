"""N09 K49 — PLATFORM_DEFAULT_TENANT / default_tenant() for knowledge harness."""
from __future__ import annotations

import re
from pathlib import Path

from core.harness.knowledge.context_bus import _resolve_graph_tenant
from core.harness.knowledge.domain_router import DomainRouter

KNOWLEDGE = Path("aiPlat-core/core/harness/knowledge")
TARGETS = [
    "aiPlat-core/core/harness/knowledge/domain_router.py",
    "aiPlat-core/core/harness/knowledge/context_bus.py",
    "aiPlat-core/core/harness/knowledge/graph.py",
    "aiPlat-core/core/harness/knowledge/scoring_engine.py",
    "aiPlat-core/core/harness/knowledge/metric_engine.py",
    "aiPlat-core/core/harness/knowledge/process_monitor.py",
    "aiPlat-core/core/harness/knowledge/staleness_monitor.py",
]


def test_platform_default_tenant_helper():
    assert DomainRouter.PLATFORM_DEFAULT_TENANT == "default"
    assert DomainRouter.default_tenant() == "default"
    assert _resolve_graph_tenant() == "default"


def test_knowledge_targets_use_default_tenant_ssot():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert (
            "default_tenant()" in text or "PLATFORM_DEFAULT_TENANT" in text
        ), rel
        assert 'tenant_id: str = "default"' not in text, rel


def test_knowledge_tenant_or_default_fallbacks_use_ssot():
    rx = re.compile(r'tenant_id[^\n]{0,80}or\s+["\']default["\']')
    hits = []
    for p in KNOWLEDGE.rglob("*.py"):
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "tenant_id = 'default'" in ln or 'tenant_id="default"' in ln:
                continue  # SQL literals — out of scope
            if rx.search(ln) and "DomainRouter.default_tenant" not in ln:
                hits.append(f"{p}:{i}:{ln.strip()}")
    assert hits == [], hits
