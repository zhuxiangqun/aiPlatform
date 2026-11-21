"""N20 L1/L2/L3 约束分层 deepen 单元测试。"""
from __future__ import annotations

from core.harness.knowledge_pipeline import constraint_layers as cl


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n20_full 恒 false；含 Gateway 热路径门。"""
    suite = cl.run_constraint_layers_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n20_full_conformance"] is False
    ids = {c["id"] for c in suite["cases"]}
    assert "hotpath_helper_attaches" in ids
    assert "gateway_hotpath_entry" in ids
    assert "put_fact_hotpath_entry" in ids
    assert "query_facts_gateway_hotpath_entry" in ids
    assert "materials_chat_hotpath_entry" in ids
    assert "graphrag_hotpath_entry" in ids

    gate = cl.evaluate_constraint_layers_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["issues"] == []


def test_hotpath_attach_and_env_off(monkeypatch):
    """Gateway/put_fact/query_facts_gateway/MaterialsChat/GraphRAG 热路径挂 n20_constraint；env=0 时跳过。"""
    monkeypatch.setenv("AIPLAT_CONSTRAINT_LAYERS_HOTPATH", "1")
    hit = cl.maybe_attach_constraint_stack_hotpath(
        {"answer": "a", "abstained": False},
        route="wiki",
        actor_permissions=["kb:read"],
    )
    assert isinstance(hit.get("n20_constraint"), dict)
    assert hit["n20_constraint"]["hotpath"] is True
    assert hit["n20_constraint"]["certified"] is False

    put = cl.maybe_attach_put_fact_constraint_hotpath(
        {"fact_id": "f1", "status": "active"},
        actor_permissions=["kb:write"],
    )
    assert put["n20_constraint"]["op"] == "put_fact"
    assert put["n20_constraint"]["enforced"] is False

    qfg = cl.maybe_attach_query_facts_gateway_constraint_hotpath(
        {"answer": "x", "abstained": False, "citations": []},
        actor_permissions=["kb:read"],
    )
    assert qfg["n20_constraint"]["op"] == "query_facts_gateway"
    assert qfg["n20_constraint"]["enforced"] is False
    assert qfg["n20_constraint"]["certified"] is False

    mc = cl.maybe_attach_materials_chat_constraint_hotpath(
        {"answer": "m", "citations": [{"source_id": "s1"}]},
        exit_kind="rag",
        actor_permissions=["kb:read"],
    )
    assert mc["n20_constraint"]["op"] == "materials_chat"
    assert mc["n20_constraint"]["exit"] == "rag"
    assert mc["n20_constraint"]["enforced"] is False
    assert mc["n20_constraint"]["certified"] is False

    gr = cl.maybe_attach_graphrag_constraint_hotpath(
        {"mode": "graphrag", "chunks": [{"source": "d1"}]},
        actor_permissions=["kb:read"],
    )
    assert gr["n20_constraint"]["op"] == "graphrag_retrieve"
    assert gr["n20_constraint"]["route"] == "graphrag"
    assert gr["n20_constraint"]["enforced"] is False
    assert gr["n20_constraint"]["certified"] is False

    monkeypatch.setenv("AIPLAT_CONSTRAINT_LAYERS_HOTPATH", "0")
    assert cl.hotpath_constraint_enabled() is False
    skip = cl.maybe_attach_constraint_stack_hotpath(
        {"answer": "b"},
        route="wiki",
        actor_permissions=["kb:read"],
    )
    assert "n20_constraint" not in skip
    skip_put = cl.maybe_attach_put_fact_constraint_hotpath({"fact_id": "f2"})
    assert "n20_constraint" not in skip_put
    skip_qfg = cl.maybe_attach_query_facts_gateway_constraint_hotpath(
        {"answer": "y"}
    )
    assert "n20_constraint" not in skip_qfg
    skip_mc = cl.maybe_attach_materials_chat_constraint_hotpath(
        {"answer": "z"}, exit_kind="shortcut"
    )
    assert "n20_constraint" not in skip_mc
    skip_gr = cl.maybe_attach_graphrag_constraint_hotpath({"mode": "vector_only"})
    assert "n20_constraint" not in skip_gr


def test_high_risk_without_l1_blocked():
    """高风险无 L1 必须阻塞。"""
    r = cl.evaluate_constraint_stack(
        risk_level="critical",
        l1_present=False,
        soft_constraints=[{"id": "p", "message": "careful"}],
    )
    assert r["blocked"] is True
    assert r["block_reason"] == "high_risk_requires_l1"
    assert r["l2_security_boundary"] is False


def test_l2_soft_does_not_block_low_risk():
    """低风险 L2 仅警告不阻塞。"""
    r = cl.evaluate_constraint_stack(
        risk_level="low",
        soft_constraints=[{"id": "style", "message": "cite"}],
        require_audit=True,
    )
    assert r["ok"] is True
    assert r["blocked"] is False
    assert "cite" in (r.get("warnings") or [])


def test_classify_layer_rejects_unknown():
    """未知层必须报错。"""
    import pytest

    with pytest.raises(cl.ConstraintLayersError):
        cl.classify_layer("L4")
    meta = cl.classify_layer("L1")
    assert meta["security_boundary"] is True
