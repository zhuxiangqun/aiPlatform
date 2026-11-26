"""生产加深 D3：SkillRouter Canary 切流/回滚。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.deployment.canary import SkillRouter
from core.harness.evo_compute.canary_bridge import (
    observe_evo_canary,
    request_evo_canary_cutover,
    rollback_evo_canary,
)
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_production_deepen_slice3_gate,
    run_evo_compute_production_deepen_slice3_suite,
)


def test_production_deepen_d3_suite_and_gate() -> None:
    suite = run_evo_compute_production_deepen_slice3_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["production_write"] is False
    assert suite["production_traffic"] is False
    assert suite["slice"] == "production-deepen-d3"
    gate = evaluate_evo_compute_production_deepen_slice3_gate(suite)
    assert gate["ok"] is True
    assert gate["g1_complete"] is False
    assert gate["production_write"] is False


def test_sandbox_cutover_observe_rollback() -> None:
    rtr = SkillRouter()
    cut = request_evo_canary_cutover(
        candidate_id="d3-unit-1",
        skill_name="evo.d3.unit",
        version="v-unit",
        canary_tenants=["tenant-a"],
        router=rtr,
        actor="unit",
    )
    assert cut["ok"] is True
    assert cut["cutover"] is True
    assert cut["production_write"] is False
    assert rtr.route("evo.d3.unit", tenant_id="tenant-a") == "v-unit"

    obs = observe_evo_canary(skill_name="evo.d3.unit", router=rtr)
    assert obs["count"] >= 1

    rb = rollback_evo_canary(
        candidate_id="d3-unit-1",
        skill_name="evo.d3.unit",
        router=rtr,
        actor="unit",
    )
    assert rb["ok"] is True
    assert rb["status"] == "rolled_back"
    assert rtr.route("evo.d3.unit", tenant_id="tenant-a") == "stable"


def test_facade_cycle_sandbox() -> None:
    cycle = facade.run_evo_canary_cutover_rollback_cycle(
        candidate_id="d3-facade-1",
        skill_name="evo.d3.facade",
        version="v-facade",
        use_global_router=False,
    )
    assert cycle["ok"] is True
    assert cycle["cycle_complete"] is True
    assert cycle["production_write"] is False
    assert cycle["certified"] is False
    suite = facade.run_evo_compute_production_deepen_slice3_suite()
    assert suite["ok"] is True
