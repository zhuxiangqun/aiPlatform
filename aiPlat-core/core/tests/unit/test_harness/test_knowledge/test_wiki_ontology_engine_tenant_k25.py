"""N09 K25 — wiki_ontology_engine GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path


def _assert_no_bare_loads(rel: str) -> None:
    text = Path(rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_wiki_ontology_engine_source_wires_tenant():
    text = Path(
        "aiPlat-core/core/api/routers/wiki_ontology_engine.py"
    ).read_text(encoding="utf-8")
    assert "def _graph_tenant()" in text
    assert "_resolve_graph_tenant" in text
    assert "GraphIndex.load(domain_id, tenant_id=_graph_tenant())" in text
    assert text.count("GraphIndex.load(domain_id, tenant_id=_graph_tenant())") == 10
    _assert_no_bare_loads("aiPlat-core/core/api/routers/wiki_ontology_engine.py")


def test_graph_tenant_helper_resolves(monkeypatch):
    from core.api.routers import wiki_ontology_engine as woe

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t25",
    )
    assert woe._graph_tenant() == "n09-t25"
