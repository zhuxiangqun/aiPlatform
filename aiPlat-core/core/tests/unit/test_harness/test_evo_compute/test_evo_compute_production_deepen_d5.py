"""生产加深 D5：D1–D4 + PSO 工程轨收口。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.deepen_closeout import (
    collect_production_deepen_track_closeout,
)
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_production_deepen_slice5_gate,
    run_evo_compute_production_deepen_slice5_suite,
)


def test_production_deepen_d5_suite_and_gate() -> None:
    suite = run_evo_compute_production_deepen_slice5_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["track_engineering_complete"] is True
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["g3_complete"] is False
    assert suite["production_write"] is False
    assert suite["slice"] == "production-deepen-d5"
    gate = evaluate_evo_compute_production_deepen_slice5_gate(suite)
    assert gate["ok"] is True
    assert gate["track_engineering_complete"] is True
    assert gate["g3_complete"] is False


def test_d5_closeout_rejects_gate_claim_leak() -> None:
    green = collect_production_deepen_track_closeout(run_suites=True)
    assert green["track_engineering_complete"] is True
    detail = green.get("slice_detail") or {}
    bad = dict(detail.get("pso") or {})
    bad["certified"] = True
    denied = collect_production_deepen_track_closeout(
        d1=detail.get("d1"),
        d2=detail.get("d2"),
        d3=detail.get("d3"),
        d4=detail.get("d4"),
        pso=bad,
        run_suites=False,
    )
    assert denied["track_engineering_complete"] is False
    assert any("gate_claim_leak" in str(m) for m in (denied.get("missing") or []))


def test_facade_d5_suite() -> None:
    suite = facade.run_evo_compute_production_deepen_slice5_suite()
    assert suite["ok"] is True
    assert suite["g3_complete"] is False
    pack = facade.collect_evo_production_deepen_track_closeout(run_suites=False)
    # without suites and without pre-fed slices → incomplete
    assert pack["track_engineering_complete"] is False
