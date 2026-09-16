"""Inference suggestion layer: no silent GraphIndex write; Action assert required."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex, GraphEdge
from core.harness.ontology_engine.graph_inference import GraphInference, InferenceResult


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def _seed_two_nodes(domain: str = "it-ops") -> None:
    g = GraphIndex(domain)
    g.add_entity("A", "node-a", "服务", source_doc_id="t")
    g.add_entity("B", "node-b", "中间件", source_doc_id="t")
    g.save()
    GraphIndex._loaded_instances.clear()


def test_apply_to_graph_refused_without_via_action(aiplat_home):
    _seed_two_nodes()
    g = GraphIndex.load("it-ops")

    class _Dom:
        inference_rules = []

    inf = InferenceResult()
    e = GraphEdge(source_id="A", target_id="B", relation_name="calls", relation_label="调用")
    e.inferred = True
    e.rule_name = "r1"
    inf.inferred_edges.append(e)

    added = GraphInference(_Dom(), g).apply_to_graph(inf)  # default via_action=False
    assert added == 0
    g2 = GraphIndex.load("it-ops")
    outs = [
        x
        for x in g2._nodes["A"].out_edges
        if x.target_id == "B" and getattr(x, "inferred", False)
    ]
    assert outs == []


@pytest.mark.asyncio
async def test_assert_inferred_edge_via_action(aiplat_home):
    _seed_two_nodes()
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_inf")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    assert reg.get("platform_action:graph:assert_inferred_edge") is not None

    r = await reg.execute(
        "platform_action:graph:assert_inferred_edge",
        ("it-ops", "A"),
        {
            "source_id": "A",
            "target_id": "B",
            "relation_name": "calls",
            "rule_name": "ut_rule",
            "inferred": True,
        },
        actor="analyst-1",
        role="analyst",
        _bypass_approval=True,
    )
    assert r.get("status") == "executed", r
    body = r.get("result") or {}
    assert body.get("inferred") is True
    assert body.get("authority") == "action_asserted"

    g = GraphIndex.load("it-ops")
    outs = [
        x
        for x in g._nodes["A"].out_edges
        if x.target_id == "B"
        and x.relation_name == "calls"
        and getattr(x, "inferred", False)
    ]
    assert len(outs) == 1
    assert outs[0].rule_name == "ut_rule"
    assert outs[0].inferred is True

    store.insert_audit.assert_awaited()
    call_args = store.insert_audit.await_args
    rec = call_args.args[0] if call_args.args else (call_args.kwargs or {})
    assert rec.get("action_id") == "platform_action:graph:assert_inferred_edge"
