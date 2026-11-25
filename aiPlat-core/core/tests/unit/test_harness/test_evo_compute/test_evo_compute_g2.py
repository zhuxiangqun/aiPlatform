"""Phase 2 / G2：离散 GA + 覆盖率诚实锁。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.safety import clear_safety_for_tests
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g2_gate,
    run_evo_compute_g2_suite,
)


def test_g2_suite_and_gate() -> None:
    suite = run_evo_compute_g2_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g2_complete"] is False
    assert suite["certified"] is False
    gate = evaluate_evo_compute_g2_gate(suite)
    assert gate["ok"] is True
    assert gate["g2_complete"] is False


def test_facade_ga_and_coverage_honesty() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    assert register_pilot_genomes(persist=False)["ok"] is True
    facade.approve_evo_budget(actor="test", persist=False)
    ga = facade.run_evo_ga_offline(
        genome_id="timeout.retry.v1",
        population_size=5,
        generations=2,
        seed=3,
    )
    assert ga["ok"] is True
    assert ga["safety_regression"] is False
    assert ga["production_write"] is False
    ev = facade.measure_evo_eval_coverage()
    assert ev["baseline_missing"] is True
    assert ev["meets_g2_threshold"] is False
    fde = facade.measure_evo_fde_evidence_coverage()
    assert fde["baseline_missing"] is True
    ready = facade.evaluate_evo_g2_exit_readiness(
        ga_ok=True,
        safety_regression_free=True,
        eval_coverage_ok=False,
        fde_coverage_ok=False,
    )
    assert ready["g2_complete"] is False
    suite = facade.run_evo_compute_g2_suite()
    assert suite["ok"] is True
