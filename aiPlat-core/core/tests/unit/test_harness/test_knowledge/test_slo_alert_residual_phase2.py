"""SLO alerting residual：告警候选；certified / Full 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    evaluate_knowledge_slo_alert_candidates,
    evaluate_knowledge_slo_alert_gate,
    run_knowledge_slo_alert_suite,
)
from core.harness.knowledge_pipeline.slo_telemetry import (
    evaluate_slo_alert_candidates,
    evaluate_slo_alert_gate,
    run_slo_alert_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = run_slo_alert_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    assert suite["attainment_ok"] is False
    assert suite.get("slo_telemetry_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "slo_alert_unavailable" in ids
    assert "slo_alert_opt_in" in ids
    gate = evaluate_slo_alert_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = evaluate_slo_alert_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_suite():
    suite = run_knowledge_slo_alert_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_slo_alert_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_alert_unavailable_default():
    r = evaluate_slo_alert_candidates("t1", include_live=False)
    assert r["status"] == "slo_alerting_unavailable"
    assert r["certified"] is False
    fr = evaluate_knowledge_slo_alert_candidates("t1", include_live=False)
    assert fr["status"] == "slo_alerting_unavailable"


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
    assert "evaluate_slo_alert_candidates" in text
    assert "run_slo_alert_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "evaluate_knowledge_slo_alert_candidates" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "slo_routes.py"
    )
    assert "evaluate-alerts" in routes.read_text(encoding="utf-8")
