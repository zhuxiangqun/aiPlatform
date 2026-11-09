"""Object-contract P0 — target contract + MatchReport matching."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_match import (
    build_match_report,
    case_spec_for_set,
    load_applicability_draft,
    match_case,
    match_eval_sets_for_target,
)
from core.apps.eval.service.target_contract import (
    SCHEMA,
    build_agent_target_contract,
    build_target_contract,
    normalize_target_contract,
)


def test_normalize_rejects_bad_object_type():
    with pytest.raises(ValueError, match="object_type"):
        normalize_target_contract(
            {"object_type": "bot", "object_id": "x", "schema": SCHEMA}
        )


def test_build_agent_contract_no_agent_id_branching():
    c = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask"],
        permissions=["read_only"],
        roles=["qa"],
    )
    assert c["schema"] == SCHEMA
    assert c["object_type"] == "agent"
    assert c["object_id"] == "qa_agent"
    assert c["object_version"] == "version_unspecified"
    assert "clarify_or_ask" in c["capabilities"]
    assert c["target_runtime"] == ["workspace_execute"]
    assert "read_only" in c["permissions"]


def test_object_type_mismatch_not_applicable():
    skill = build_target_contract(
        object_type="skill",
        object_id="demo.skill",
        target_runtime=["core_skill_execute"],
    )
    spec = case_spec_for_set("default/normal")
    row = match_case(skill, spec)
    assert row["decision"] == "not_applicable"
    assert any("object_type_mismatch" in r for r in row["reasons"])


def test_explicit_missing_capability_not_applicable():
    agent = build_agent_target_contract(
        object_id="plain_agent",
        capabilities=[],
        permissions=["read_only"],
        eval_profile={"profile_source": "explicit", "capabilities": [], "permissions": ["read_only"]},
    )
    row = match_case(agent, case_spec_for_set("default/missing_info"))
    assert row["decision"] == "not_applicable"
    # Capability ID Map v1: legacy clarify_or_ask → canonical clarification
    assert any("missing_capability:clarification" in r for r in row["reasons"])


def test_derived_hints_missing_capability_stays_selected():
    """§0.7: derived_hints gaps are unconfirmed — must not alone drive N/A."""
    agent = build_agent_target_contract(
        object_id="qa_agent",
        eval_profile={
            "profile_source": "derived_hints",
            "capabilities": [],
            "permissions": ["read_only"],
            "boundaries": {"derived": True},
        },
    )
    row = match_case(agent, case_spec_for_set("default/missing_info"))
    assert row["decision"] == "selected"
    assert any("capability_unconfirmed:clarification" in r for r in row["reasons"])
    assert not any(r.startswith("missing_capability:") for r in row["reasons"])


def test_unknown_profile_missing_capability_stays_selected():
    agent = build_agent_target_contract(
        object_id="plain_agent",
        capabilities=[],
        permissions=["read_only"],
    )
    row = match_case(agent, case_spec_for_set("default/tool_failure"))
    assert row["decision"] == "selected"
    assert any("capability_unconfirmed:error_recovery" in r for r in row["reasons"])


def test_high_risk_refuse_or_handoff_keeps_read_only_applicable():
    agent = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=[],
        permissions=["read_only"],  # no shell
    )
    row = match_case(agent, case_spec_for_set("default/high_risk"))
    assert row["decision"] == "selected"
    assert row["obligation_exception_applied"] is True


def test_multi_turn_requires_capability():
    agent = build_agent_target_contract(
        object_id="mem_agent",
        capabilities=["multi_turn_memory"],
    )
    row = match_case(agent, case_spec_for_set("default/multi_turn"))
    assert row["decision"] == "selected"


def test_match_report_for_suite_explainable():
    agent = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask", "error_recovery"],
        permissions=["read_only"],
        eval_profile={
            "profile_source": "explicit",
            "capabilities": ["clarify_or_ask", "error_recovery"],
            "permissions": ["read_only"],
        },
    )
    draft = load_applicability_draft()
    assert draft.get("schema") == "eval.case_applicability_draft.v1"
    report = match_eval_sets_for_target(
        agent,
        [
            "default/normal",
            "default/missing_info",
            "default/tool_failure",
            "default/high_risk",
            "default/multi_turn",
        ],
    )
    assert report["schema"] == "eval.match_report.v1"
    assert report["phase"] == "p0_advisory"
    selected_ids = {x["set_id"] for x in report["selected_cases"]}
    excluded_ids = {x["set_id"] for x in report["excluded_cases"]}
    assert "default/normal" in selected_ids
    assert "default/missing_info" in selected_ids
    assert "default/high_risk" in selected_ids  # refuse_or_handoff
    assert "default/multi_turn" in excluded_ids  # explicit lacks multi_turn_memory
    assert report["counts"]["selected"] + report["counts"]["not_applicable"] == 5


def test_build_match_report_empty_requires_ok():
    agent = build_agent_target_contract(object_id="a")
    report = build_match_report(agent, [case_spec_for_set("default/normal")])
    assert report["counts"]["selected"] == 1
