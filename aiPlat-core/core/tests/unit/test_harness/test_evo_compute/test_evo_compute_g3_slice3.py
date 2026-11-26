"""Phase 3 / G3 slice-3：HUMAN_GATE 100% + 闭环 L4 报告。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g3_slice3_gate,
    run_evo_compute_g3_slice3_suite,
)


def test_g3_slice3_suite_and_gate() -> None:
    suite = run_evo_compute_g3_slice3_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g3_complete"] is False
    assert suite["slice"] == "g3-slice3"
    gate = evaluate_evo_compute_g3_slice3_gate(suite)
    assert gate["ok"] is True
    assert gate["g3_complete"] is False


def test_facade_hitl_and_l4() -> None:
    audit = facade.audit_evo_human_gate_coverage(
        [
            {
                "candidate_id": "x",
                "status": "production",
                "human_gate_passed": True,
                "human_gate_actor": "a",
                "human_gate_evidence_ref": "e",
            }
        ]
    )
    assert audit["human_gate_100"] is True
    assert audit["g3_complete"] is False
    report = facade.build_evo_loops_l4_assessment_report(
        levels={"governance": 4, "knowledge": 4, "eval": 4, "fde": 4},
        measured=False,
    )
    assert report["loops_l4_or_waiver"] is True
    assert report["certified"] is False
    suite = facade.run_evo_compute_g3_slice3_suite()
    assert suite["ok"] is True
