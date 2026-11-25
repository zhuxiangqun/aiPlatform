"""Phase 0 / G0 受控演化底座单元测试。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g0_gate,
    run_evo_compute_g0_suite,
)


def test_g0_suite_and_gate_pass() -> None:
    clear_registry_for_tests()
    suite = run_evo_compute_g0_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["phase0_complete"] is False
    gate = evaluate_evo_compute_g0_gate(suite)
    assert gate["ok"] is True
    assert gate["phase0_complete"] is False


def test_facade_g0_surface() -> None:
    clear_registry_for_tests()
    suite = facade.run_evo_compute_g0_suite()
    assert suite["ok"] is True
    gate = facade.evaluate_evo_compute_g0_gate(suite)
    assert gate["ok"] is True
    base = facade.measure_closed_loop_baseline(owner="test-owner", persist=False)
    assert base["ok"] is True
    assert base["baseline_missing"] is True
    assert base["upgrade_claimed"] is False
