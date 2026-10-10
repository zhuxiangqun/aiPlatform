"""MaterialsChat delivery mode — high risk must not seal as success."""

from __future__ import annotations

from core.apps.agents.materials_chat import _delivery_gate_block, _is_delivery_mode


def test_qa_mode_not_delivery():
    assert _is_delivery_mode({}) is False
    assert _is_delivery_mode({"mode": "chat"}) is False


def test_delivery_mode_flags():
    assert _is_delivery_mode({"mode": "delivery"}) is True
    assert _is_delivery_mode({"delivery_mode": "task"}) is True
    assert _is_delivery_mode({"mode": "governed"}) is True


def test_delivery_gate_blocks_high_risk():
    out = _delivery_gate_block(
        vars0={"mode": "delivery"},
        quality="low_evidence",
        hallucination_meta={"hallucination_risk": 0.8},
        output={"answer": "maybe"},
        metadata={"intent": "qa"},
    )
    assert out is not None
    assert out.success is False
    assert out.error == "delivery_gate_blocked"
    assert (out.output or {}).get("delivery_gate", {}).get("blocked") is True


def test_delivery_gate_allows_low_risk():
    out = _delivery_gate_block(
        vars0={"mode": "delivery"},
        quality="ok",
        hallucination_meta={"hallucination_risk": 0.1},
        output={"answer": "grounded"},
        metadata={},
    )
    assert out is None


def test_qa_mode_never_blocks():
    out = _delivery_gate_block(
        vars0={"mode": "chat"},
        quality="low_evidence",
        hallucination_meta={"hallucination_risk": 0.9},
        output={"answer": "x"},
        metadata={},
    )
    assert out is None
