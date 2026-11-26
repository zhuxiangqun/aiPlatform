"""PSO 离线基线对照。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.pso import compare_pso_vs_de_es, run_pso_offline
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_pso_baseline_gate,
    run_evo_compute_pso_baseline_suite,
)


def test_pso_baseline_suite_and_gate() -> None:
    suite = run_evo_compute_pso_baseline_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["baseline_only"] is True
    assert suite["g1_complete"] is False
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    gate = evaluate_evo_compute_pso_baseline_gate(suite)
    assert gate["ok"] is True
    assert gate["g1_complete"] is False


def test_pso_offline_and_compare() -> None:
    register_pilot_genomes(persist=False)
    pso = run_pso_offline(
        genome_id="routing.weights.v1", swarm_size=5, iterations=3, seed=3
    )
    assert pso["ok"] is True
    assert pso["baseline_only"] is True
    assert pso["production_write"] is False
    cmp = compare_pso_vs_de_es(
        genome_id="routing.weights.v1",
        population_size=5,
        generations=3,
        seed=5,
    )
    assert cmp["ok"] is True
    assert cmp["pso_claimed_superior"] is False


def test_facade_pso() -> None:
    register_pilot_genomes(persist=False)
    out = facade.run_evo_pso_offline(
        genome_id="routing.weights.v1", swarm_size=4, iterations=2, seed=9
    )
    assert out["ok"] is True
    suite = facade.run_evo_compute_pso_baseline_suite()
    assert suite["ok"] is True
