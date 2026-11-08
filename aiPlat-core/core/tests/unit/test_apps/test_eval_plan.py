"""Evaluation Plan compiler — object-contract P2."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_pack_legacy import (
    ManifestValidationError,
    apply_manifest_sampling,
    expand_sets_to_manifest,
)
from core.apps.eval.service.eval_plan import (
    PLAN_SCHEMA,
    PLAN_SCHEMA_V2,
    compile_evaluation_plan,
)
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
    assert plan["schema"] == PLAN_SCHEMA == PLAN_SCHEMA_V2
    assert plan["plan_id"].startswith("plan-")
    assert plan["sample_manifest"]
    assert all("hash" in row for row in plan["sample_manifest"])
    selected = {x["set_id"] for x in plan["selected_cases"]}
    excluded = {x["set_id"]: x for x in plan["excluded_cases"]}
    assert "default/normal" in selected
    assert "default/missing_info" in selected
    assert "default/high_risk" in excluded  # special deferred
    assert excluded["default/high_risk"]["status"] == "untested"
    assert "default/multi_turn" in excluded
    assert excluded["default/multi_turn"]["status"] == "untested"
    assert plan["claims_policy"]["accuracy_claim"] is False
    # high_risk / multi_turn deferred → not in execution manifest
    man_sets = {row.get("set_id") for row in plan["sample_manifest"]}
    assert "default/high_risk" not in man_sets
    assert "default/multi_turn" not in man_sets


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
    assert any("capability_unconfirmed:clarification" in r for r in miss_row["reasons"])


def test_stratified_seed_stable_and_group_intact():
    man, _, _ = expand_sets_to_manifest(
        ["default/normal", "default/noise", "default/multi_turn"]
    )
    a, meta_a = apply_manifest_sampling(
        man, strategy="stratified", sample_n=6, seed=42, min_per_stratum=1
    )
    b, meta_b = apply_manifest_sampling(
        man, strategy="stratified", sample_n=6, seed=42, min_per_stratum=1
    )
    assert [r["case_id"] for r in a] == [r["case_id"] for r in b]
    assert meta_a["quota_trace"]
    # multi_turn group must stay intact if any of its cases are selected
    mt = [r for r in a if r.get("session_group") == "default/multi_turn"]
    if mt:
        full_mt = [r for r in man if r.get("session_group") == "default/multi_turn"]
        assert {r["case_id"] for r in mt} == {r["case_id"] for r in full_mt}


def test_stratified_shortfall_error_or_degrade():
    man, _, _ = expand_sets_to_manifest(["default/normal"])
    # Impossible min_per_stratum
    with pytest.raises(ManifestValidationError, match="shortfall"):
        apply_manifest_sampling(
            man,
            strategy="stratified",
            sample_n=1,
            seed=1,
            min_per_stratum=999,
            on_insufficient="error",
        )
    sampled, meta = apply_manifest_sampling(
        man,
        strategy="stratified",
        sample_n=1,
        seed=1,
        min_per_stratum=999,
        on_insufficient="degrade",
    )
    assert meta["degraded"] is True
    assert meta["degraded_reasons"]
    assert len(sampled) <= len(man)


def test_compile_plan_stratified_writes_quota_trace():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask", "error_recovery"],
        permissions=["read_only"],
    )
    plan = compile_evaluation_plan(
        c,
        purpose=["behavior", "regression"],
        selection_strategy="stratified",
        sample_n=4,
        seed=7,
        min_per_stratum=1,
        on_insufficient="degrade",
    )
    assert plan["selection"]["strategy"] == "stratified"
    assert plan["selection"]["quota_trace"]
    assert plan["sample_manifest"]
    assert len(plan["sample_manifest"]) <= 4 or plan["selection"].get("degraded")
