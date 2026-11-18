"""N09 K43 — ai-knowledge / tracking request fallbacks via DomainRouter."""
from __future__ import annotations

from pathlib import Path

WIKI_OE = Path("aiPlat-core/core/api/routers/wiki_ontology_engine.py")
FACADE = Path("aiPlat-core/core/api/core_facade.py")
PIPELINE = Path("aiPlat-core/core/harness/execution/pipeline_engine.py")
AGENTS = Path("aiPlat-core/core/api/routers/agents.py")
ACTIONS = Path("aiPlat-platform/apps/fde/api/action_routes.py")
RETRIEVAL = Path("aiPlat-core/core/harness/syscalls/retrieval.py")


def test_wiki_ontology_engine_req_fallbacks_use_helper():
    text = WIKI_OE.read_text(encoding="utf-8")
    assert "def _kb_domain()" in text
    assert "def _req_domain_id(" in text
    assert 'req.get("domain_id", "ai-knowledge")' not in text
    assert text.count("domain_id = _req_domain_id(req)") >= 13
    assert '["ai-knowledge", "default", "ship-design"]' not in text
    assert '"ship-design"' not in text
    assert "list_domains()" in text


def test_facade_pipeline_agents_kb_fallback():
    assert "default_kb_domain()" in FACADE.read_text(encoding="utf-8")
    assert 'or "ai-knowledge"' not in FACADE.read_text(encoding="utf-8")
    assert "default_kb_domain()" in PIPELINE.read_text(encoding="utf-8")
    assert 'or "ai-knowledge"' not in PIPELINE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    assert "default_kb_domain()" in agents
    assert 'domain_id", "ai-knowledge"' not in agents


def test_action_routes_tracking_fallback():
    text = ACTIONS.read_text(encoding="utf-8")
    assert "fde_graph_domain()" in text
    assert 'or "fde-delivery"' not in text


def test_retrieval_circuit_breaker_graph_domain():
    text = RETRIEVAL.read_text(encoding="utf-8")
    assert "default_graph_domain()" in text
    # circuit-breaker domain fallback must not keep bare default
    assert 'domain_id=domain_id or "default"' not in text
