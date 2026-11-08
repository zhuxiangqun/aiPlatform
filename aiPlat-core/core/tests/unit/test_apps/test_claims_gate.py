"""L5 claims gate — scope-bound unlock; default false."""
from __future__ import annotations

from core.apps.eval.service.claims_gate import (
    DEFAULT_MIN_SAMPLE_N,
    evaluate_l5_claims_gate,
    claims_policy_stub,
)


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
    }
    base.update(overrides)
    return base


def test_claims_policy_stub_always_false():
    p = claims_policy_stub(thin=True, profile_source="derived_hints")
    assert p["accuracy_claim"] is False
    assert p["sufficiency_claim"] is False
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
