"""生产加深 D4：活台账 HITL + 已测 L4/缓释签批。"""
from __future__ import annotations

from core.api import core_facade as facade
from core.harness.evo_compute.candidate_ledger import (
    clear_ledger_for_tests,
    record_human_gate_decision,
)
from core.harness.evo_compute.deepen_signoff import (
    clear_d4_signoff_for_tests,
    collect_production_deepen_d4_pack,
    sign_production_deepen_d4,
)
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_production_deepen_slice4_gate,
    run_evo_compute_production_deepen_slice4_suite,
)


def test_production_deepen_d4_suite_and_gate() -> None:
    suite = run_evo_compute_production_deepen_slice4_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["e2_claimed"] is False
    assert suite["g3_complete"] is False
    assert suite["production_write"] is False
    assert suite["slice"] == "production-deepen-d4"
    gate = evaluate_evo_compute_production_deepen_slice4_gate(suite)
    assert gate["ok"] is True
    assert gate["g3_complete"] is False


def test_d4_signoff_requires_pack_ready() -> None:
    clear_ledger_for_tests()
    clear_d4_signoff_for_tests()
    pack = collect_production_deepen_d4_pack(measured=False)
    assert pack["pack_ready"] is False
    denied = sign_production_deepen_d4(
        actor="x", evidence_ref="e", pack=pack, persist=False
    )
    assert denied["ok"] is False
    assert denied["error"] == "pack_not_ready"

    record_human_gate_decision(
        candidate_id="d4-u1",
        status="approved",
        actor="a",
        evidence_ref="e1",
        persist=False,
    )
    levels = {"governance": 4, "knowledge": 4, "eval": 4, "fde": 4}
    ready_pack = collect_production_deepen_d4_pack(levels=levels, measured=True)
    assert ready_pack["pack_ready"] is True
    signed = sign_production_deepen_d4(
        actor="owner",
        evidence_ref="d4:unit",
        pack=ready_pack,
        persist=False,
    )
    assert signed["ok"] is True
    assert signed["d4_signed"] is True
    assert signed["g3_complete"] is False


def test_facade_d4_suite() -> None:
    suite = facade.run_evo_compute_production_deepen_slice4_suite()
    assert suite["ok"] is True
    assert suite["g3_complete"] is False
