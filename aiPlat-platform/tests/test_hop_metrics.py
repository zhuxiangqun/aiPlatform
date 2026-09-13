"""Phase C W5: hop metrics + promotion aggregation."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def _load_hop_metrics():
    path = ROOT / "aiPlat-platform" / "builder" / "hop_metrics.py"
    spec = importlib.util.spec_from_file_location("hop_metrics_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_and_aggregate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    hm = _load_hop_metrics()
    record_hop = hm.record_hop
    aggregate_hops = hm.aggregate_hops
    evaluate_project_run_through = hm.evaluate_project_run_through

    pid = "prj_hop_demo"
    for i in range(20):
        record_hop(pid, skill="s1", agent="a1", ok=True)
    # one failure with stage
    record_hop(pid, skill="s1", agent="a1", ok=False, failed_stage="tool_selection", error="x")
    # one failure without stage — excluded from effective rate, blocks attribution
    record_hop(pid, skill="s1", agent="a1", ok=False, failed_stage="", error="orphan")

    agg = aggregate_hops(pid)
    assert agg["n_runs"] == 22
    assert agg["failures_missing_stage"] == 1
    assert agg["effective_n"] == 21
    assert agg["by_failed_stage"].get("tool_selection") == 1

    blocked = evaluate_project_run_through(
        pid,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
    )
    assert blocked["ok"] is False
    assert any("failed_stage" in b for b in blocked["blockers"])

    # clean project: all failures attributed → can go green
    pid2 = "prj_hop_green"
    for _ in range(19):
        record_hop(pid2, skill="s1", ok=True)
    record_hop(pid2, skill="s1", ok=False, failed_stage="planning")
    # 19/20 = 0.95 >= 0.80
    record_hop(pid2, skill="s1", ok=True)
    promo = evaluate_project_run_through(
        pid2,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
    )
    assert promo["ok"] is True, promo
    assert "不做无门控互调" in (promo.get("policy") or "")


def test_below_threshold_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    hm = _load_hop_metrics()
    record_hop = hm.record_hop
    evaluate_project_run_through = hm.evaluate_project_run_through

    pid = "prj_low"
    for _ in range(10):
        record_hop(pid, skill="s", ok=True)
    for _ in range(10):
        record_hop(pid, skill="s", ok=False, failed_stage="planning")
    promo = evaluate_project_run_through(
        pid,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
    )
    assert promo["ok"] is False
    assert any("e2e_success_rate" in b for b in promo["blockers"])


def test_derive_test_evidence_from_report():
    hm = _load_hop_metrics()
    derive = hm.derive_test_evidence

    empty = derive(last_test_report=None, state=None)
    assert empty["real_tests_green"] is False
    assert empty["physical_evidence"] is False

    flag_only = derive(state={"_real_tests_ok": True})
    assert flag_only["real_tests_green"] is True
    assert flag_only["physical_evidence"] is False  # 无产物不算物理证据

    green = derive(
        last_test_report={
            "test_passed": True,
            "test_report": {"meta": {"pass_rate": 1.0}, "cases": [{"name": "t1"}]},
            "e2e_smoke": {"passed": True},
        }
    )
    assert green["real_tests_green"] is True
    assert green["physical_evidence"] is True

    failed = derive(
        last_test_report={
            "test_passed": False,
            "test_report": {"meta": {"pass_rate": 0.0}},
            "e2e_smoke": {"passed": False, "reason": "boom"},
        }
    )
    assert failed["real_tests_green"] is False
    assert failed["physical_evidence"] is False
