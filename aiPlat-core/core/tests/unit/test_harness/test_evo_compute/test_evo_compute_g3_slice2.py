"""Phase 3 / G3 slice-2：GP 强类型 DSL 沙箱。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g3_slice2_gate,
    run_evo_compute_g3_slice2_suite,
)


def test_g3_slice2_suite_and_gate() -> None:
    suite = run_evo_compute_g3_slice2_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["g3_complete"] is False
    assert suite["slice"] == "g3-slice2"
    gate = evaluate_evo_compute_g3_slice2_gate(suite)
    assert gate["ok"] is True
    assert gate["g3_complete"] is False


def test_facade_gp_rejects_core_code() -> None:
    bad = facade.validate_evo_gp_dsl(
        {"root": {"type": "rule", "python": "import os", "children": []}}
    )
    assert bad["ok"] is False
    assert bad["dsl_only"] is False
    gp = facade.run_evo_gp_offline(population_size=4, generations=2, seed=1)
    assert gp["ok"] is True
    assert gp["dsl_only"] is True
    assert gp["emits_core_code"] is False
    suite = facade.run_evo_compute_g3_slice2_suite()
    assert suite["ok"] is True
