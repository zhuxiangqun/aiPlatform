"""N09 K44 — signature default domain_id via DomainRouter.PLATFORM_KB_DOMAIN."""
from __future__ import annotations

import re
from pathlib import Path

TARGETS = [
    "aiPlat-core/core/apps/agents/multi_agent_orchestrator.py",
    "aiPlat-core/core/api/routers/diagnostics.py",
    "aiPlat-core/core/api/routers/knowledge_graph.py",
    "aiPlat-core/core/harness/knowledge/okf_exporter.py",
    "aiPlat-core/core/harness/knowledge/ontology_query_mapper.py",
    "aiPlat-core/core/harness/knowledge/wiki_engine.py",
    "aiPlat-core/core/harness/execution/router.py",
    "aiPlat-core/core/harness/ontology_engine/knowledge_gap_detector.py",
    "aiPlat-core/core/harness/ontology_engine/cleanup.py",
    "aiPlat-core/core/harness/ontology_engine/engine.py",
]


def test_targets_use_platform_kb_domain_default():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "DomainRouter.PLATFORM_KB_DOMAIN" in text, rel
        assert 'domain_id: str = "ai-knowledge"' not in text, rel


def test_production_ai_knowledge_signature_defaults_empty():
    rx = re.compile(r'domain_id\s*:\s*str\s*=\s*["\']ai-knowledge["\']')
    hits = []
    for root in (Path("aiPlat-core/core"), Path("aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits


def test_fde_ask_and_export_use_ssot():
    ask = Path("aiPlat-platform/apps/fde/api/fde_ask.py").read_text(encoding="utf-8")
    assert "PLATFORM_KB_DOMAIN" in ask
    assert 'else "ai-knowledge"' not in ask
    fde = Path("aiPlat-platform/apps/fde/api/fde.py").read_text(encoding="utf-8")
    assert "fde_kb_domain()" in fde
    assert 'domain_id", "ai-knowledge"' not in fde
