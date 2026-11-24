"""N08 Lv4 bounded auto-close residual：certified / full_action_lv4 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    evaluate_bounded_lv4_auto_close,
    evaluate_bounded_lv4_auto_close_gate,
    run_bounded_lv4_auto_close_suite,
)
from core.harness.knowledge_pipeline.lv4_bounded_auto_close import (
    evaluate_bounded_lv4_auto_close as _eval,
    evaluate_bounded_lv4_auto_close_gate as _gate,
    run_bounded_lv4_auto_close_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["full_action_lv4"] is False
    assert suite.get("n08_action_policy_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "lv4_auto_close_unavailable" in ids
    assert "lv4_auto_close_opt_in" in ids
    assert "honesty_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["full_action_lv4"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_full_action_lv4_forbidden" in honesty2["issues"]


def test_facade_suite():
    suite = run_bounded_lv4_auto_close_suite()
    assert suite["ok"] is True
    gate = evaluate_bounded_lv4_auto_close_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["full_action_lv4"] is False


def test_unavailable_default():
    r = _eval(
        action_id="a1",
        total=100,
        false_positives=0,
        rollback_action_id="rb1",
        risk_level="low",
        action_level="lv4_auto_close",
        min_samples=10,
    )
    assert r["status"] == "lv4_auto_close_unavailable"
    assert r["certified"] is False
    assert r["full_action_lv4"] is False
    fr = evaluate_bounded_lv4_auto_close(
        action_id="a1",
        total=100,
        false_positives=0,
        rollback_action_id="rb1",
        min_samples=10,
    )
    assert fr["status"] == "lv4_auto_close_unavailable"


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "lv4_bounded_auto_close.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "evaluate_bounded_lv4_auto_close" in text
    assert "run_bounded_lv4_auto_close_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "evaluate_bounded_lv4_auto_close" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "lv4_false_positive_routes.py"
    )
    assert "lv4-auto-close/evaluate" in routes.read_text(encoding="utf-8")
    cat = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "n24-conformance-catalog.yaml"
    )
    assert "n08_action_policy_freeze" in cat.read_text(encoding="utf-8")
