"""Appendix B hash vectors + Plan v2 manifest fail-closed (Case Pack P0)."""
from __future__ import annotations

import copy

import pytest

from core.apps.eval.service.case_pack_hash import (
    case_hash_payload,
    compute_case_hash,
    compute_execution_fingerprint,
    compute_manifest_hash,
    compute_pack_hash,
)
from core.apps.eval.service.case_pack_legacy import (
    ClaimEligibilityError,
    ManifestValidationError,
    assert_claim_eligible_allowed,
    expand_sets_to_manifest,
    require_sample_manifest,
    task_dict_to_case,
)
from core.apps.eval.service.eval_plan import (
    PLAN_SCHEMA_V2,
    compile_evaluation_plan,
    project_plan_to_v1,
)
from core.apps.eval.service.target_contract import build_agent_target_contract


def _fixture_a() -> dict:
    return {
        "applies_to": {},
        "case_id": "fixture-a-001",
        "category": "normal",
        "difficulty": "medium",
        "expected_steps": [],
        "expected_tools": ["code_generation"],
        "forbidden_tools": [],
        "holdout": False,
        "oracle": {},
        "prompt": "echo hello",
        "provenance": {
            "generator": "manual",
            "generator_version": "0",
            "seed": None,
        },
        "requires": {},
        "risk_level": "low",
        "rubric": {"type": "lexical", "must_contain": ["hello"]},
        "session_group": None,
        "tags": ["normal"],
    }


def test_appendix_b_case_hash_fixture_a():
    h = compute_case_hash(_fixture_a())
    assert h == (
        "sha256:f82bc84cdd2b83fb4dd01c8ec5985abfa1bea44c3f1e77906c0d0660cca80c61"
    )


def test_appendix_b_review_notes_excluded():
    a = _fixture_a()
    a2 = copy.deepcopy(a)
    a2["review"] = {"notes": "changed", "status": "approved"}
    assert compute_case_hash(a) == compute_case_hash(a2)


def test_appendix_b_prompt_change_alters_hash():
    a = _fixture_a()
    a2 = copy.deepcopy(a)
    a2["prompt"] = "echo hello!"
    assert compute_case_hash(a2) == (
        "sha256:9b1046c3de99d194f2d0c2e27d03c489199f5e0034b702357c0ff54de07f3916"
    )
    assert compute_case_hash(a) != compute_case_hash(a2)


def test_appendix_b_pack_order_independent():
    a = _fixture_a()
    b = copy.deepcopy(a)
    b["case_id"] = "fixture-a-002"
    b["prompt"] = "echo world"
    b["rubric"] = {"type": "lexical", "must_contain": ["world"]}
    assert compute_case_hash(b) == (
        "sha256:457fda9cde2ec70ff82c821e633858ce226dec2f0b64ea708078b4eda4930703"
    )
    kwargs = dict(
        pack_id="fixture.pack",
        version="1.0.0",
        kind="frozen",
        claim_eligible=False,
        scope="global",
        object_types=["agent"],
    )
    h1 = compute_pack_hash(**kwargs, cases=[a, b])
    h2 = compute_pack_hash(**kwargs, cases=[b, a])
    assert h1 == h2 == (
        "sha256:fab6005f50da43f7bbf393a6adc6d9703af67ad16a03443ba4e219db9373806b"
    )


def test_plan_emits_v2_with_nonempty_manifest():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask", "error_recovery", "multi_turn_memory"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(c, purpose=["behavior", "regression"])
    assert plan["schema"] == PLAN_SCHEMA_V2
    assert plan["sample_manifest"]
    assert plan["manifest_hash"].startswith("sha256:")
    assert plan["execution_fingerprint"].startswith("exec-")
    assert plan["selection"]["mode"] == "legacy_sets"
    assert plan["counts"]["manifest_cases"] == len(plan["sample_manifest"])
    # Runner entry accepts the compiled plan
    m = require_sample_manifest(plan)
    assert len(m) == len(plan["sample_manifest"])
    # Fingerprint split: run_key changes exec only
    e1 = compute_execution_fingerprint(
        plan_id=plan["plan_id"],
        manifest_hash=plan["manifest_hash"],
        run_key="ui#1",
    )
    e2 = compute_execution_fingerprint(
        plan_id=plan["plan_id"],
        manifest_hash=plan["manifest_hash"],
        run_key="ui#2",
    )
    assert e1 != e2
    assert compute_manifest_hash(m) == plan["manifest_hash"]


def test_v2_empty_manifest_fail_closed():
    with pytest.raises(ManifestValidationError):
        require_sample_manifest(
            {"schema": PLAN_SCHEMA_V2, "sample_manifest": [], "selected_cases": []}
        )


def test_generated_claim_eligible_rejected():
    with pytest.raises(ClaimEligibilityError):
        assert_claim_eligible_allowed(kind="generated", claim_eligible=True)
    assert_claim_eligible_allowed(kind="frozen", claim_eligible=False)
    assert_claim_eligible_allowed(kind="frozen", claim_eligible=True)


def test_project_plan_to_v1_not_execution_list():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(c, purpose=["behavior"])
    v1 = project_plan_to_v1(plan)
    assert v1["schema"] == "eval.evaluation_plan.v1"
    assert v1.get("projected_from") == "v2"
    assert "sample_manifest" not in v1


def test_multi_turn_session_group_intact():
    manifest, _, cov = expand_sets_to_manifest(["default/multi_turn"])
    assert manifest
    groups = {row.get("session_group") for row in manifest}
    assert groups == {"default/multi_turn"}
    assert cov["sets"]["default/multi_turn"]["session_group"] == "default/multi_turn"


def test_task_map_prompt_priority():
    case = task_dict_to_case(
        {
            "task_id": "t1",
            "user_input": "old",
            "prompt": "new",
            "success_criteria": {"must_contain": ["x"]},
            "category": "normal",
        },
        set_id="default/normal",
    )
    assert case["prompt"] == "new"
    assert case["rubric"]["type"] == "lexical"
    # review excluded from hash payload
    payload = case_hash_payload({**case, "review": {"notes": "n"}})
    assert "review" not in payload
