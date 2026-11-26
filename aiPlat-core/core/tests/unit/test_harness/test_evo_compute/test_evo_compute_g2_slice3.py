"""Phase 2 / G2 slice-3：冻结回归集自动回归门。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.safety import clear_safety_for_tests
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g2_slice3_gate,
    run_evo_compute_g2_slice3_suite,
)


def test_g2_slice3_suite_and_gate() -> None:
    suite = run_evo_compute_g2_slice3_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g2_complete"] is False
    assert suite["slice"] == "g2-slice3"
    gate = evaluate_evo_compute_g2_slice3_gate(suite)
    assert gate["ok"] is True
    assert gate["g2_complete"] is False


def test_facade_regression_gate_honesty() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    assert register_pilot_genomes(persist=False)["ok"] is True
    facade.approve_evo_budget(actor="test", persist=False)
    rset = facade.get_evo_regression_set(genome_id="timeout.retry.v1")
    assert rset["frozen"] is True
    assert rset["production_sample"] is False
    # 同基因对比应过门
    genes = {"max_retries": 2, "timeout_ms": 1500}
    gate = facade.run_evo_regression_gate(
        genome_id="timeout.retry.v1",
        baseline_genes=genes,
        challenger_genes=dict(genes),
    )
    assert gate["ok"] is True
    assert gate["feeds_evolution"] is False
    assert gate["g2_complete"] is False
    assert gate["passed"] is True
    suite = facade.run_evo_compute_g2_slice3_suite()
    assert suite["ok"] is True
