"""N09 K45 — signature default domain_id via PLATFORM_DEFAULT_GRAPH_DOMAIN."""
from __future__ import annotations

import re
from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


TARGETS = [
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/api/routers/agents.py",
    "aiPlat-core/core/api/routers/wiki_ontology_sql.py",
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py",
    "aiPlat-core/core/harness/evaluation/rag_diagnostics_collector.py",
    "aiPlat-core/core/harness/infrastructure/gates/cross_validation_gate.py",
    "aiPlat-core/core/harness/infrastructure/gates/semantic_gate.py",
    "aiPlat-core/core/harness/knowledge/active_synthesis.py",
    "aiPlat-core/core/harness/knowledge/ontology_constraint_compiler.py",
    "aiPlat-core/core/harness/knowledge/provenance.py",
    "aiPlat-core/core/harness/knowledge/semantic_cache.py",
    "aiPlat-core/core/harness/knowledge/sql_ontology.py",
    "aiPlat-core/core/harness/knowledge_pipeline/extractor.py",
    "aiPlat-core/core/harness/knowledge_pipeline/fact_ledger.py",
    "aiPlat-core/core/harness/knowledge_pipeline/retriever.py",
    "aiPlat-core/core/harness/learning/experience_vector.py",
    "aiPlat-core/core/harness/ontology_engine/graph_importer.py",
    "aiPlat-core/core/harness/ontology_engine/knowledge_synthesis.py",
    "aiPlat-core/core/harness/ontology_engine/state_history.py",
    "aiPlat-core/core/harness/ontology_engine/traversal_cache.py",
    "aiPlat-core/core/harness/syscalls/evaluation.py",
    "aiPlat-core/core/harness/syscalls/graph.py",
    "aiPlat-core/core/harness/syscalls/graph_extract.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
]


def test_targets_use_platform_default_graph_domain():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "PLATFORM_DEFAULT_GRAPH_DOMAIN" in text, rel
        assert 'domain_id: str = "default"' not in text, rel


def test_production_default_domain_signature_defaults_empty():
    rx = re.compile(r'domain_id\s*:\s*str\s*=\s*["\']default["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits


def test_tenant_default_literal_deferred_outside_knowledge_ssot():
    """K45 left tenant alone; K49 SSOT covers harness/knowledge — outer layers may still literal."""
    text = (_repo_root() / "aiPlat-core/core/harness/syscalls/retrieval.py").read_text(encoding="utf-8")
    # Still a signature default somewhere outside knowledge SSOT batch (honest residual).
    assert "tenant_id" in text
