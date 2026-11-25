"""Phase 2 / G2 slice-2：库存/报告实测覆盖路径。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g2_slice2_gate,
    run_evo_compute_g2_slice2_suite,
)


def test_g2_slice2_suite_and_gate() -> None:
    suite = run_evo_compute_g2_slice2_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g2_complete"] is False
    assert suite["slice"] == "g2-slice2"
    gate = evaluate_evo_compute_g2_slice2_gate(suite)
    assert gate["ok"] is True
    assert gate["g2_complete"] is False


def test_facade_inventory_and_report_bridge() -> None:
    ev = facade.measure_evo_eval_coverage_from_inventory(
        required_ids=[f"c{i}" for i in range(10)],
        covered_ids=[f"c{i}" for i in range(9)],
    )
    assert ev["baseline_missing"] is False
    assert ev["meets_g2_threshold"] is True

    fde = facade.measure_evo_fde_evidence_coverage_from_inventory(
        required_ids=[f"e{i}" for i in range(20)],
        covered_ids=[f"e{i}" for i in range(19)],
    )
    assert fde["meets_g2_threshold"] is True

    # 空用例库 → 报告可算但 covered 可能为 0；桥接不得炸
    bridged = facade.collect_evo_eval_coverage_from_capability_report(
        subject_kind="agent",
        cases=[],
        min_per_capability=1,
    )
    assert bridged.get("ok") is True
    assert bridged.get("certified") is False
    assert bridged.get("bridged_via") == "eval_analyze_capability_coverage"

    suite = facade.run_evo_compute_g2_slice2_suite()
    assert suite["ok"] is True
    assert suite["g2_complete"] is False
