"""SLO 告警产品面：默认可用；certified / attainment_ok 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    evaluate_knowledge_slo_alert_candidates,
    evaluate_knowledge_slo_alert_candidates_product,
    evaluate_knowledge_slo_alert_product_gate,
    run_knowledge_slo_alert_product_suite,
)
from core.harness.knowledge_pipeline.slo_telemetry import (
    evaluate_slo_alert_product_gate as _gate,
    record_slo_sample,
    run_slo_alert_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["attainment_ok"] is False
    assert suite["slo_alert_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "slo_alert_product_eval" in ids
    assert "slo_alert_product_unavailable" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["attainment_ok"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_attainment_on_alert_forbidden" in honesty2["issues"]


def test_facade_product_suite():
    suite = run_knowledge_slo_alert_product_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_slo_alert_product_gate(suite)
    assert gate["ok"] is True
    assert gate["slo_alert_product_surface"] is True
    assert gate["certified"] is False


def test_product_without_residual_env(tmp_path):
    os.environ.pop("AIPLAT_KNOWLEDGE_SLO_ALERT", None)
    db = str(tmp_path / "slo.db")
    record_slo_sample(
        "action_success_rate",
        0.0,
        tenant_id="slo-product-t",
        ok=False,
        db_path=db,
    )
    residual = evaluate_knowledge_slo_alert_candidates(
        "slo-product-t", db_path=db, include_live=False
    )
    assert residual["status"] == "slo_alerting_unavailable"
    assert residual.get("via") == "env_disabled"
    assert residual.get("slo_alert_product_surface") is False

    product = evaluate_knowledge_slo_alert_candidates_product(
        "slo-product-t", db_path=db, include_live=False
    )
    assert product["status"] == "ok"
    assert product.get("via") == "product"
    assert product["slo_alert_product_surface"] is True
    assert product["certified"] is False
    assert product["attainment_ok"] is False
    assert int(product.get("alert_count") or 0) >= 1


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "slo_telemetry.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "evaluate_slo_alert_candidates_product" in text
    assert "run_slo_alert_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "evaluate_knowledge_slo_alert_candidates_product" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "slo_routes.py"
    )
    assert "slo/product/evaluate-alerts" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "SloAlertPanel.tsx"
    )
    assert "slo/product/evaluate-alerts" in panel.read_text(encoding="utf-8")
