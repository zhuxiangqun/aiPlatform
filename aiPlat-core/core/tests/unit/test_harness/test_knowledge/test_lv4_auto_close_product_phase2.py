"""N08 有界 Lv4 auto-close 产品面：默认可用；full_action_lv4 / certified 恒 false。"""
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
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["full_action_lv4"] is False
    assert suite["lv4_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "lv4_auto_close_product_eval" in ids
    assert "lv4_auto_close_product_high_risk_denied" in ids
    assert "honesty_product_certified_false" in ids
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


def test_facade_product_suite():
    suite = run_bounded_lv4_auto_close_product_suite()
    assert suite["ok"] is True
    gate = evaluate_bounded_lv4_auto_close_product_gate(suite)
    assert gate["ok"] is True
    assert gate["lv4_product_surface"] is True
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
    assert product["full_action_lv4"] is False


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
    assert "run_bounded_lv4_auto_close_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "evaluate_bounded_lv4_auto_close_product" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "lv4_false_positive_routes.py"
    )
    assert "lv4-auto-close/product/evaluate" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "Lv4AutoClosePanel.tsx"
    )
    assert "lv4-auto-close/product/evaluate" in panel.read_text(encoding="utf-8")
