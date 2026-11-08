"""L5 claims gate — scope-bound unlock; default false."""
from __future__ import annotations

from core.apps.eval.service.claims_gate import (
    DEFAULT_MIN_SAMPLE_N,
    evaluate_l5_claims_gate,
    claims_policy_stub,
    pack_claim_disclosure_from_plan,
)
from core.apps.eval.service.eval_plan import attach_evaluation_plan, compile_evaluation_plan
from core.apps.eval.service.target_contract import build_agent_target_contract


def _full_scope(**overrides):
    base = {
        "object_type": "agent",
        "object_id": "qa_agent",
        "object_version": "v1",
        "runtime_tier": "workspace_execute",
        "plan_id": "plan-xyz",
        "set_ids": ["default/normal"],
        "oracle_types": ["lexical_must_contain"],
        "dimensions": ["task_result"],
        "sample_n": DEFAULT_MIN_SAMPLE_N,
        "has_run_evidence": True,
        "untested_applicable_n": 0,
        "runtime_claim": True,
        "human_review": True,
        "claim_eligible": True,
    }
    base.update(overrides)
    return base


def test_claims_policy_stub_always_false():
    p = claims_policy_stub(thin=True, profile_source="derived_hints")
    assert p["accuracy_claim"] is False
    assert p["sufficiency_claim"] is False
    assert p["claim_eligible"] is False
    assert "unlock_ref" in p


def test_fixture_never_eligible():
    r = evaluate_l5_claims_gate(_full_scope(runtime_tier="fixture", runtime_claim=False))
    assert r["accuracy_eligible"] is False
    assert r["accuracy_claim"] is False
    assert "fixture_runtime_not_l5" in r["failed"]


def test_incomplete_coverage_blocks():
    r = evaluate_l5_claims_gate(_full_scope(untested_applicable_n=2))
    assert r["accuracy_eligible"] is False
    assert "incomplete_coverage_untested" in r["failed"]


def test_authorize_without_gates_stays_false():
    r = evaluate_l5_claims_gate({"sample_n": 1}, explicit_authorize=True)
    assert r["accuracy_claim"] is False
    assert r["sufficiency_claim"] is False


def test_full_gates_with_authorize():
    r = evaluate_l5_claims_gate(_full_scope(), explicit_authorize=True)
    assert r["accuracy_eligible"] is True
    assert r["sufficiency_eligible"] is True
    assert r["accuracy_claim"] is True
    assert r["sufficiency_claim"] is True
    assert r["claims_policy"]["accuracy_claim"] is True


def test_accuracy_eligible_sufficiency_needs_review():
    r = evaluate_l5_claims_gate(
        _full_scope(human_review=False, calibrated_rubric=False),
        explicit_authorize=True,
    )
    assert r["accuracy_eligible"] is True
    assert r["sufficiency_eligible"] is False
    assert r["accuracy_claim"] is True
    assert r["sufficiency_claim"] is False


def test_claim_eligible_false_blocks_accuracy():
    r = evaluate_l5_claims_gate(
        _full_scope(claim_eligible=False), explicit_authorize=True
    )
    assert r["accuracy_eligible"] is False
    assert r["accuracy_claim"] is False
    assert "pack_not_claim_eligible" in r["failed"]


def test_claim_eligible_unspecified_blocks():
    scope = _full_scope()
    del scope["claim_eligible"]
    r = evaluate_l5_claims_gate(scope, explicit_authorize=True)
    assert r["accuracy_claim"] is False
    assert "claim_eligible_unspecified" in r["failed"]


def test_pack_disclosure_on_attach_plan():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(c, purpose=["behavior"])
    out = attach_evaluation_plan({"ok": True, "accuracy_claim": True}, plan)
    disc = out["pack_claim_disclosure"]
    assert disc["schema"] == "eval.pack_claim_disclosure.v1"
    assert "pack_kinds" in out
    assert out["claim_eligible"] is False  # compile defaults claim_eligible false
    assert out["accuracy_claim"] is False  # forced off when packs not eligible
    assert pack_claim_disclosure_from_plan(plan)["claim_eligible"] is False
