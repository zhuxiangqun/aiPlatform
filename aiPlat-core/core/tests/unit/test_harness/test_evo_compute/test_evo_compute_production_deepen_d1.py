"""生产加深 D1：活源摘要 + 台账审计。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.candidate_ledger import clear_ledger_for_tests
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_production_deepen_slice1_gate,
    run_evo_compute_production_deepen_slice1_suite,
)


def test_production_deepen_d1_suite_and_gate() -> None:
    clear_ledger_for_tests()
    suite = run_evo_compute_production_deepen_slice1_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g3_complete"] is False
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["slice"] == "production-deepen-d1"
    gate = evaluate_evo_compute_production_deepen_slice1_gate(suite)
    assert gate["ok"] is True
    assert gate["g3_complete"] is False


def test_facade_ledger_and_deepen_collect() -> None:
    clear_ledger_for_tests()
    rec = facade.record_evo_human_gate_decision(
        candidate_id="facade-cand",
        status="production",
        actor="owner",
        evidence_ref="hg:f",
        persist=False,
    )
    assert rec["ok"] is True
    audit = facade.audit_evo_human_gate_from_ledger()
    assert audit["source"] == "ledger"
    assert audit["human_gate_100"] is True
    assert audit["g3_complete"] is False

    deepen = facade.collect_evo_production_deepen_slice1(
        fde_inventory={
            "required_ids": [f"e.{i}" for i in range(20)],
            "covered_ids": [f"e.{i}" for i in range(19)],
        },
        include_canary_probe=False,
        skip_eval_bridge=True,
    )
    assert deepen["ok"] is True
    assert deepen["eval_coverage"]["available"] is False
    assert deepen["fde_coverage"]["available"] is True
    assert deepen["canary_probe"]["cutover"] is False
    assert deepen["g3_complete"] is False
    assert deepen["certified"] is False

    suite = facade.run_evo_compute_production_deepen_slice1_suite()
    assert suite["ok"] is True
