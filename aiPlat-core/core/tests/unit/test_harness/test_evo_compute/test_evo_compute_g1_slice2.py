"""Phase 1 / G1 slice-2：三试点 DE/ES 电池。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.pilots import PILOT_GENOME_IDS
from core.harness.evo_compute.safety import clear_safety_for_tests
from core.harness.evo_compute.suite import run_evo_compute_g1_slice2_suite


def test_g1_slice2_suite() -> None:
    suite = run_evo_compute_g1_slice2_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g1_complete"] is False
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    summary = suite.get("battery_summary") or {}
    assert summary.get("meets_repro_gate") is True
    assert summary.get("meets_lineage_gate") is True
    assert summary.get("meets_hard_gate") is True
    assert summary.get("meets_holdout_gate") is True


def test_facade_pilot_battery() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    facade.approve_evo_budget(actor="test", persist=False)
    bat = facade.run_evo_pilot_de_es_battery(
        algorithms=["de"],
        population_size=5,
        generations=2,
        seed=11,
        register_pilots=True,
        run_holdout=True,
    )
    assert bat["ok"] is True
    assert set(bat.get("genome_ids") or []) == set(PILOT_GENOME_IDS)
    assert bat["summary"]["reproducible_rate"] >= 0.95
    assert bat["summary"]["lineage_min"] >= 1.0
    assert bat["production_write"] is False
    assert bat["g1_complete"] is False
    suite = facade.run_evo_compute_g1_slice2_suite()
    assert suite["ok"] is True
