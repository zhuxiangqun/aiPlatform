"""N08 Lv4 误报门重设计 deepen 单元测试。"""
from __future__ import annotations

from core.harness.knowledge_pipeline import lv4_false_positive_gate as lv4


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n08_full 恒 false；redesigned=true。"""
    suite = lv4.run_lv4_false_positive_gate_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n08_full_conformance"] is False
    assert suite["lv4_gate_redesigned"] is True

    gate = lv4.evaluate_lv4_false_positive_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["lv4_gate_redesigned"] is True
    assert gate["issues"] == []


def test_zero_samples_cannot_auto_close():
    """0 样本不得假绿放行。"""
    r = lv4.evaluate_lv4_fp_gate(
        action_id="a",
        total=0,
        false_positives=0,
        rollback_action_id="rb",
        min_samples=10,
    )
    assert r["allowed"] is False
    assert "insufficient_history" in r["reason"]
    assert r["fp_rate"] is None


def test_missing_rollback_denied():
    """有样本但无 rollback 拒绝。"""
    r = lv4.evaluate_lv4_fp_gate(
        action_id="a",
        total=50,
        false_positives=0,
        rollback_action_id="",
        min_samples=10,
    )
    assert r["allowed"] is False
    assert "rollback" in r["reason"]


def test_healthy_path_allowed():
    """足样本 + 低误报 + rollback → 允许。"""
    r = lv4.evaluate_lv4_fp_gate(
        action_id="a",
        total=100,
        false_positives=0,
        rollback_action_id="rb",
        fp_rate_max=0.005,
        min_samples=10,
    )
    assert r["allowed"] is True
    assert r["gate_version"] == "v2"
    assert r["certified"] is False
