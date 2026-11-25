"""Phase 0 / G0 slice-2：三试点 / 预算 / 安全 / 夹具回放 / 出口就绪。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.budget import (
    approve_budget,
    check_budget,
    clear_budget_for_tests,
    get_budget_policy,
)
from core.harness.evo_compute.exit_readiness import evaluate_g0_exit_readiness
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.pilots import PILOT_GENOME_IDS, register_pilot_genomes
from core.harness.evo_compute.replay import replay_candidate_offline
from core.harness.evo_compute.safety import (
    clear_safety_for_tests,
    get_safety_boundary,
    sign_safety_boundary,
)
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g0_gate,
    run_evo_compute_g0_suite,
)


def test_g0_suite_includes_slice2() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    suite = run_evo_compute_g0_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["phase0_complete"] is False
    assert suite["certified"] is False
    ids = set(suite.get("pilot_genome_ids") or [])
    assert set(PILOT_GENOME_IDS).issubset(ids)
    gate = evaluate_evo_compute_g0_gate(suite)
    assert gate["ok"] is True
    assert gate["phase0_complete"] is False


def test_pilots_budget_safety_replay_exit() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()

    pilots = register_pilot_genomes(persist=False)
    assert pilots["ok"] is True
    assert pilots["count"] == 3
    assert pilots["pilots_determined"] is True

    bud = get_budget_policy()
    assert bud["approved"] is False
    over = check_budget({"candidates": 9999, "cost_usd": 100})
    assert over["within_budget"] is False
    assert over["auto_stop"] is True

    saf = get_safety_boundary()
    assert saf["signed"] is False

    rep = replay_candidate_offline(
        genome_id="routing.weights.v1",
        genes={"semantic_weight": 0.4, "cost_weight": 0.3, "latency_weight": 0.3},
        persist_evidence=False,
    )
    assert rep["ok"] is True
    assert rep["status"] == "ranked"
    assert rep["production_sample"] is False

    ready = evaluate_g0_exit_readiness(replay_ok=True, baseline_ok=True)
    assert ready["phase0_complete"] is False
    assert "budget_approved" in ready["missing"]
    assert "safety_signed" in ready["missing"]

    # 人工签字后出口可为 True（仍不宣称 certified/e2）
    assert approve_budget(actor="budget-owner", persist=False)["ok"] is True
    assert sign_safety_boundary(actor="security-owner", persist=False)["ok"] is True
    ready2 = evaluate_g0_exit_readiness(replay_ok=True, baseline_ok=True)
    assert ready2["phase0_complete"] is True
    assert ready2["certified"] is False
    assert ready2["e2_claimed"] is False


def test_facade_slice2_surface() -> None:
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    pilots = facade.register_evo_pilot_genomes(persist=False)
    assert pilots["ok"] is True
    assert facade.get_evo_budget_policy()["approved"] is False
    assert facade.check_evo_budget({"candidates": 1})["within_budget"] is True
    assert facade.get_evo_safety_boundary()["signed"] is False
    rep = facade.replay_evo_candidate_offline(
        genome_id="routing.weights.v1",
        genes={"semantic_weight": 0.5, "cost_weight": 0.3, "latency_weight": 0.2},
        persist_evidence=False,
    )
    assert rep["ok"] is True
    ready = facade.evaluate_evo_g0_exit_readiness(replay_ok=True)
    assert ready["phase0_complete"] is False
