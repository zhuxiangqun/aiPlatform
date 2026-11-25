"""Phase 1 / G1：DE/ES 离线 Orchestrator + holdout + 演练。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.orchestrator import run_de_es_offline
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.safety import clear_safety_for_tests
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g1_gate,
    run_evo_compute_g1_suite,
)


def test_g1_suite_and_gate() -> None:
    suite = run_evo_compute_g1_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g1_complete"] is False
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    gate = evaluate_evo_compute_g1_gate(suite)
    assert gate["ok"] is True
    assert gate["g1_complete"] is False


def test_de_es_reproducible_and_lineage() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    assert register_pilot_genomes(persist=False)["ok"] is True
    approve_budget(actor="test", persist=False)
    a = run_de_es_offline(
        genome_id="routing.weights.v1",
        algorithm="de",
        population_size=6,
        generations=2,
        seed=99,
    )
    b = run_de_es_offline(
        genome_id="routing.weights.v1",
        algorithm="de",
        population_size=6,
        generations=2,
        seed=99,
    )
    assert a["ok"] and b["ok"]
    assert a["lineage_completeness"] >= 1.0
    assert a["hard_constraint_regressions"] == 0
    # 同种子：初始指纹与代数路径应一致（候选 id 含 uuid，比 fingerprint 集）
    fp_a = sorted(p["fingerprint"] for p in a["population"])
    fp_b = sorted(p["fingerprint"] for p in b["population"])
    assert fp_a == fp_b
    assert a["production_write"] is False


def test_facade_g1_surface() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    facade.register_evo_pilot_genomes(persist=False)
    facade.approve_evo_budget(actor="test", persist=False)
    de = facade.run_evo_de_es_offline(
        genome_id="routing.weights.v1",
        algorithm="es",
        population_size=5,
        generations=2,
        seed=3,
    )
    assert de["ok"] is True
    best = (de.get("ranked_candidates") or [{}])[0]
    hold = facade.compare_evo_holdout(
        genome_id="routing.weights.v1",
        baseline_genes={"semantic_weight": 0.33, "cost_weight": 0.33, "latency_weight": 0.34},
        challenger_genes=dict(best.get("genes") or {}),
        n_batches=3,
        seed=1,
    )
    assert hold["ok"] is True
    assert hold["certified"] is False
    drill = facade.run_evo_human_gate_canary_rollback_drill(candidate_id="facade-drill")
    assert drill["ok"] is True
    suite = facade.run_evo_compute_g1_suite()
    assert suite["ok"] is True
    gate = facade.evaluate_evo_compute_g1_gate(suite)
    assert gate["ok"] is True
    assert gate["g1_complete"] is False
