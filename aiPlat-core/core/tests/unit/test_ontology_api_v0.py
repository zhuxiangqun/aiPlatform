"""Ontology API v0 adapter — envelope shape + schema alignment."""
from __future__ import annotations

import json
from pathlib import Path

from core.harness.knowledge.ontology_api import (
    SCHEMA_VERSION,
    attach_ontology_api,
    from_graph_health,
    from_structured_query,
    from_wiki_pages,
    to_ontology_api_v0,
    to_ontology_healthz,
)


def test_to_ontology_api_v0_required():
    env = to_ontology_api_v0(kind="entity", payload={"id": "e1"}, domain_id="demo")
    assert env["schema_version"] == SCHEMA_VERSION
    assert env["kind"] == "entity"
    assert env["domain_id"] == "demo"
    assert env["payload"]["id"] == "e1"


def test_from_structured_query_and_attach():
    raw = {"result": {"title": "RAG"}, "template_used": "concept", "confidence": 0.9}
    env = from_structured_query(raw, domain_id="default")
    assert env["kind"] == "query_result"
    out = attach_ontology_api(dict(raw), env)
    assert out["ontology_api"]["schema_version"] == SCHEMA_VERSION
    assert out["template_used"] == "concept"


def test_from_wiki_pages_and_graph_health():
    wiki = from_wiki_pages([{"title": "A"}], query="q", collection_id="default")
    assert wiki["kind"] == "wiki"
    assert wiki["payload"]["total"] == 1
    graph = from_graph_health({"domain": "d1", "exists": True, "node_count": 3}, domain_id="d1")
    assert graph["kind"] == "graph"
    assert graph["domain_id"] == "d1"


def test_ontology_healthz_shape():
    hz = to_ontology_healthz(status="healthy", domains=2, mode="read_only")
    assert hz["status"] == "ok"
    assert hz["product_id"] == "ontology"
    assert hz["domains"] == 2
    assert hz["deploy_unit"] == "central"


def test_matches_repo_schema():
    repo = Path(__file__).resolve().parents[4]
    schema_path = (
        repo
        / "reports/five-products/modules/ontology/contracts/schemas/ontology_api.schema.json"
    )
    assert schema_path.is_file(), schema_path
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = to_ontology_api_v0(
        kind="query_result",
        payload={"entities": [], "relations": []},
        domain_id="example",
        refs=[],
    )
    for k in schema.get("required") or []:
        assert k in sample
    assert sample["schema_version"] == schema["properties"]["schema_version"]["const"]
