"""SEC-P5: T11 deferred gate + OOS extension disclosure."""
from __future__ import annotations

from core.apps.eval.service.security_p5_extensions import (
    build_oos_extension_disclosure,
    evaluate_deep_supply_chain_boundary,
    evaluate_t11_deferred_gate,
    load_p5_extension_gates,
    security_sec_p5_status,
)


def test_gates_seed_loads():
    g = load_p5_extension_gates()
    assert g["schema"] == "eval.security_p5_extension_gates.v1"
    assert g["accuracy_claim"] is False
    assert g["security_certification"] is False
    assert "t11_deferred" in g
    assert len(g["t11_deferred"]["graduate_requires_all"]) >= 4


def test_t11_default_stays_deferred():
    gate = evaluate_t11_deferred_gate(evidence={})
    assert gate["deferred"] is True
    assert gate["graduated"] is False
    assert gate["status"] == "deferred_m2"
    assert gate["accuracy_claim"] is False
    assert "OOS-05" in gate["related_oos"]
    assert not all(c["ok"] for c in gate["checks"])


def test_t11_graduates_only_when_all_conditions_met():
    partial = evaluate_t11_deferred_gate(
        evidence={
            "multi_agent_runtime_wired": True,
            "handoff_session_trace_harness": True,
            "fixture_count": 5,
            "human_authorize_graduate": False,
        }
    )
    assert partial["deferred"] is True
    assert partial["graduated"] is False

    full = evaluate_t11_deferred_gate(
        evidence={
            "multi_agent_runtime_wired": True,
            "handoff_session_trace_harness": True,
            "fixture_count": 5,
            "human_authorize_graduate": True,
            "human_reviewer": "sec-qa",
        }
    )
    assert full["graduated"] is True
    assert full["deferred"] is False
    assert full["status"] == "graduated_engineering"
    assert full["security_certification"] is False
    assert full["claim_eligible"] is False


def test_oos_extension_cards_disclose_poison_and_deep_mcp():
    disc = build_oos_extension_disclosure()
    assert disc["any_claimable"] is False
    assert "OOS-01" in disc["oos_ids"]
    assert "OOS-06" in disc["oos_ids"]
    assert "OOS-05" in disc["oos_ids"]
    ids = {c["card_id"] for c in disc["cards"]}
    assert "model_poison_training_extraction" in ids
    assert "deep_mcp_supply_chain" in ids
    assert "t11_multi_agent" in ids
    assert "t13_escape" in ids


def test_t13_shallow_does_not_cover_deep_oos():
    b = evaluate_deep_supply_chain_boundary(t13_shallow_ok=True)
    assert b["t13_shallow_ok"] is True
    assert b["deep_covered"] is False
    assert b["deep_oos"] == "OOS-06"
    assert b["boundary_holds"] is True
    assert b["process_split_authorized"] is False
    assert b["accuracy_claim"] is False


def test_p5_status_and_facade():
    st = security_sec_p5_status()
    assert st["slice"] == "SEC-P5"
    assert st["t11"]["deferred"] is True
    assert st["oos_extensions"]["oos_ids"]
    assert st["accuracy_claim"] is False
    assert st["security_certification"] is False
    assert st["claim_eligible"] is False
    assert st["process_split_authorized"] is False

    from core.api.core_facade import (
        eval_build_oos_extension_disclosure,
        eval_evaluate_deep_supply_chain_boundary,
        eval_evaluate_t11_deferred_gate,
        eval_load_p5_extension_gates,
        eval_security_sec_p5_status,
    )

    assert eval_load_p5_extension_gates()["schema"] == "eval.security_p5_extension_gates.v1"
    assert eval_security_sec_p5_status()["ok"] is True
    assert eval_evaluate_t11_deferred_gate()["deferred"] is True
    assert eval_build_oos_extension_disclosure()["any_claimable"] is False
    assert eval_evaluate_deep_supply_chain_boundary(t13_shallow_ok=True)["deep_covered"] is False
