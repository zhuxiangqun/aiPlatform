"""N20 L1/L2/L3 约束分层 deepen 单元测试。"""
from __future__ import annotations

from core.harness.knowledge_pipeline import constraint_layers as cl


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n20_full 恒 false。"""
    suite = cl.run_constraint_layers_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n20_full_conformance"] is False

    gate = cl.evaluate_constraint_layers_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["issues"] == []


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
