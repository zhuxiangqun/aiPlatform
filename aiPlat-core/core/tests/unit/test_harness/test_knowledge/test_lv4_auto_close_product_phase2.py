"""N08 有界 Lv4 auto-close 产品面：low|medium+审批；full_action_lv4 / certified 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    evaluate_bounded_lv4_auto_close,
    evaluate_bounded_lv4_auto_close_product,
    evaluate_bounded_lv4_auto_close_product_gate,
    run_bounded_lv4_auto_close_product_suite,
)
from core.harness.knowledge_pipeline.lv4_bounded_auto_close import (
    evaluate_bounded_lv4_auto_close_product_gate as _gate,
    run_bounded_lv4_auto_close_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["full_action_lv4"] is False
    assert suite["lv4_product_surface"] is True
    assert suite["lv4_medium_approval_product"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "lv4_auto_close_product_eval" in ids
    assert "lv4_auto_close_product_high_risk_denied" in ids
    assert "lv4_auto_close_product_medium_denied_without_approval" in ids
    assert "lv4_auto_close_product_medium_ok_with_gates" in ids
    assert "lv4_auto_close_product_medium_kill_switch_active" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    assert gate["lv4_medium_approval_product"] is True
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
    bad3 = dict(suite)
    bad3["lv4_medium_approval_product"] = False
    honesty3 = _gate(bad3)
    assert honesty3["ok"] is False
    assert "product_lv4_medium_approval_required" in honesty3["issues"]


def test_facade_product_suite():
    suite = run_bounded_lv4_auto_close_product_suite()
    assert suite["ok"] is True
    gate = evaluate_bounded_lv4_auto_close_product_gate(suite)
    assert gate["ok"] is True
    assert gate["lv4_product_surface"] is True
    assert gate["lv4_medium_approval_product"] is True
    assert gate["full_action_lv4"] is False


def test_product_without_residual_env():
    os.environ.pop("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE", None)
    residual = evaluate_bounded_lv4_auto_close(
        action_id="n08-ui",
        total=100,
        false_positives=0,
        rollback_action_id="rb",
        risk_level="low",
        action_level="lv4_auto_close",
        min_samples=10,
    )
    assert residual["status"] == "lv4_auto_close_unavailable"
    product = evaluate_bounded_lv4_auto_close_product(
        action_id="n08-ui",
        total=100,
        false_positives=0,
        rollback_action_id="rb",
        risk_level="low",
        action_level="lv4_auto_close",
        min_samples=10,
    )
    assert product["status"] == "ok"
    assert product["via"] == "product"
    assert product["auto_close_allowed"] is True
    assert product["lv4_product_surface"] is True
    assert product["lv4_medium_approval_product"] is True
    assert product["full_action_lv4"] is False


def test_product_medium_requires_gates():
    os.environ.pop("AIPLAT_ACTION_KILL_SWITCH", None)
    bare = evaluate_bounded_lv4_auto_close_product(
        action_id="n08-med",
        total=100,
        false_positives=0,
        rollback_action_id="rb",
        risk_level="medium",
        action_level="lv4_auto_close",
        min_samples=10,
    )
    assert bare["auto_close_allowed"] is False
    assert bare["reason"] == "approval_attested_required"
    ok = evaluate_bounded_lv4_auto_close_product(
        action_id="n08-med",
        total=100,
        false_positives=0,
        rollback_action_id="rb",
        risk_level="medium",
        action_level="lv4_auto_close",
        min_samples=10,
        approval_attested=True,
        kill_switch_clear=True,
    )
    assert ok["status"] == "ok"
    assert ok["auto_close_allowed"] is True
    assert ok["risk_level"] == "medium"


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
    assert "evaluate_bounded_lv4_auto_close_product" in text
    assert "lv4_medium_approval_product" in text
    assert "approval_attested" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "approval_attested" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "lv4_false_positive_routes.py"
    )
    rtext = routes.read_text(encoding="utf-8")
    assert "lv4-auto-close/product/evaluate" in rtext
    assert "approval_attested" in rtext
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "Lv4AutoClosePanel.tsx"
    )
    ptext = panel.read_text(encoding="utf-8")
    assert "lv4-auto-close/product/evaluate" in ptext
    assert "approval_attested" in ptext
    assert "kill_switch_clear" in ptext
