"""Evaluation Plan compiler — object-contract P2."""
from __future__ import annotations

from core.apps.eval.service.eval_plan import PLAN_SCHEMA, compile_evaluation_plan
from core.apps.eval.service.target_contract import build_agent_target_contract


def test_plan_defaults_core_capability_defers_special_without_purpose():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask", "error_recovery", "multi_turn_memory"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(
        c,
        purpose=["behavior", "regression"],
        include_special=False,
    )
    assert plan["schema"] == PLAN_SCHEMA
    assert plan["plan_id"].startswith("plan-")
    selected = {x["set_id"] for x in plan["selected_cases"]}
    excluded = {x["set_id"]: x for x in plan["excluded_cases"]}
    assert "default/normal" in selected
    assert "default/missing_info" in selected
    assert "default/high_risk" in excluded  # special deferred
    assert excluded["default/high_risk"]["status"] == "untested"
    assert "default/multi_turn" in excluded
    assert excluded["default/multi_turn"]["status"] == "untested"
    assert plan["claims_policy"]["accuracy_claim"] is False


def test_plan_includes_special_when_purpose_has_safety():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask", "multi_turn_memory"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(
        c,
        purpose=["behavior", "safety", "reliability"],
    )
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert "default/high_risk" in selected  # refuse_or_handoff + safety purpose
    assert "default/multi_turn" in selected


def test_plan_marks_explicit_capability_mismatch_not_applicable():
    c = build_agent_target_contract(
        object_id="plain",
        capabilities=[],
        permissions=["read_only"],
        eval_profile={
            "profile_source": "explicit",
            "capabilities": [],
            "permissions": ["read_only"],
        },
    )
    plan = compile_evaluation_plan(
        c,
        purpose=["behavior", "safety"],
        include_special=True,
    )
    excluded = {x["set_id"]: x for x in plan["excluded_cases"]}
    assert excluded["default/missing_info"]["status"] == "not_applicable"
    assert "default/normal" in {x["set_id"] for x in plan["selected_cases"]}
    assert "default/high_risk" in {x["set_id"] for x in plan["selected_cases"]}


def test_plan_derived_hints_do_not_na_capability_gaps():
    """Screenshot regression: skills/tools 推导缺失 ≠ not_applicable."""
    c = build_agent_target_contract(
        object_id="qa_agent",
        eval_profile={
            "profile_source": "derived_hints",
            "capabilities": [],
            "permissions": ["read_only"],
            "boundaries": {"derived": True, "note": "hints from skills/tools"},
        },
    )
    plan = compile_evaluation_plan(
        c,
        purpose=["behavior", "regression", "safety", "reliability"],
        include_special=False,
    )
    selected = {x["set_id"] for x in plan["selected_cases"]}
    excluded = {x["set_id"]: x for x in plan["excluded_cases"]}
    assert "default/missing_info" in selected
    assert "default/tool_failure" in selected
    assert "default/multi_turn" in selected  # special allowed by reliability/safety
    assert "default/missing_info" not in excluded
    assert plan.get("eval_profile_source") == "derived_hints"
    miss_row = next(x for x in plan["selected_cases"] if x["set_id"] == "default/missing_info")
    assert any("capability_unconfirmed:clarify_or_ask" in r for r in miss_row["reasons"])
