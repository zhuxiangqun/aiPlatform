"""eval_profile resolve / capability hints — no agent_id branching."""
from __future__ import annotations

from core.apps.eval.service.eval_profile_resolve import (
    build_eval_profile_from_declarations,
    derive_capability_hints,
)
from core.apps.eval.service.eval_plan import compile_plan_for_object


def test_derive_hints_from_skill_tokens():
    caps = derive_capability_hints(
        skills=["clarify_dialog", "memory_store", "tool_failure_recover"],
        tools=[],
    )
    assert "clarify_or_ask" in caps
    assert "multi_turn_memory" in caps
    assert "error_recovery" in caps


def test_explicit_eval_profile_wins():
    profile = build_eval_profile_from_declarations(
        skills=["memory_store"],
        config={
            "eval_profile": {
                "capabilities": ["code_gen"],
                "permissions": ["shell"],
            }
        },
    )
    assert profile["profile_source"] == "explicit"
    assert profile["capabilities"] == ["code_gen"]
    assert "shell" in profile["permissions"]


def test_derived_profile_feeds_plan_selection():
    profile = build_eval_profile_from_declarations(
        skills=["clarify_helper", "error_recovery_kit"],
        permissions=["read_only"],
    )
    assert profile["profile_source"] == "derived_hints"
    plan = compile_plan_for_object(
        object_type="agent",
        object_id="any_agent",
        purpose=["behavior", "regression", "safety"],
        eval_profile=profile,
    )
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert "default/normal" in selected
    assert "default/missing_info" in selected
    assert "default/tool_failure" in selected
    assert "default/high_risk" in selected  # refuse_or_handoff
    assert plan.get("eval_profile_source") == "derived_hints"
    assert (plan.get("target_contract") or {}).get("profile_source") == "derived_hints"


def test_derived_profile_empty_caps_still_selects_capability_packs():
    profile = build_eval_profile_from_declarations(
        skills=["unrelated_skill"],
        tools=[],
        permissions=["read_only"],
    )
    assert profile["profile_source"] == "derived_hints"
    assert "clarify_or_ask" not in profile["capabilities"]
    plan = compile_plan_for_object(
        object_type="agent",
        object_id="qa_agent",
        purpose=["behavior", "regression", "safety", "reliability"],
        eval_profile=profile,
    )
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert "default/missing_info" in selected
    assert "default/tool_failure" in selected
    assert "default/multi_turn" in selected
    assert not any(
        x.get("status") == "not_applicable"
        and x.get("set_id") in {"default/missing_info", "default/tool_failure", "default/multi_turn"}
        for x in plan["excluded_cases"]
    )


def test_explicit_profile_source_on_plan():
    plan = compile_plan_for_object(
        object_type="agent",
        object_id="locked_agent",
        purpose=["behavior"],
        eval_profile={
            "profile_source": "explicit",
            "capabilities": ["clarify_or_ask"],
            "permissions": ["read_only"],
        },
    )
    assert plan.get("eval_profile_source") == "explicit"
