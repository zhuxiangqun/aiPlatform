"""Phase C W5: hop metrics + promotion aggregation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def test_record_and_aggregate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from builder.hop_metrics import record_hop, aggregate_hops, evaluate_project_run_through

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
    from builder.hop_metrics import record_hop, evaluate_project_run_through

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
