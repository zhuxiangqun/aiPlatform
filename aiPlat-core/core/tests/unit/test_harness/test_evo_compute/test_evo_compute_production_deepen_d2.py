"""生产加深 D2：holdout 分区数据集。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_production_deepen_slice2_gate,
    run_evo_compute_production_deepen_slice2_suite,
)


def test_production_deepen_d2_suite_and_gate() -> None:
    suite = run_evo_compute_production_deepen_slice2_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["production_traffic"] is False
    assert suite["slice"] == "production-deepen-d2"
    gate = evaluate_evo_compute_production_deepen_slice2_gate(suite)
    assert gate["ok"] is True
    assert gate["g1_complete"] is False


def test_facade_holdout_dataset_compare() -> None:
    register_pilot_genomes(persist=False)
    part = facade.load_evo_holdout_partition(
        "routing.weights.v1", prefer_disk=False, allow_seed_fallback=True
    )
    assert part["available"] is True
    assert part["production_traffic"] is False
    cmp = facade.compare_evo_holdout(
        genome_id="routing.weights.v1",
        baseline_genes={
            "semantic_weight": 0.5,
            "cost_weight": 0.3,
            "latency_weight": 0.2,
        },
        challenger_genes={
            "semantic_weight": 0.6,
            "cost_weight": 0.2,
            "latency_weight": 0.2,
        },
        holdout_partition=part,
        allow_surrogate_fallback=False,
    )
    assert cmp["ok"] is True
    assert str(cmp.get("source") or "").startswith("dataset")
    assert cmp["certified"] is False
    suite = facade.run_evo_compute_production_deepen_slice2_suite()
    assert suite["ok"] is True
