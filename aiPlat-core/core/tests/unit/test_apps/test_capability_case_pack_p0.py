"""Case Pack P0 — capability id map, test_purpose, AgentSubjectAdapter."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_id_map import (
    UnknownCapabilityId,
    is_v1_in_scope,
    resolve_capability_id,
    resolve_capability_ids,
)
from core.apps.eval.service.case_match import match_case
from core.apps.eval.service.subject_adapter import (
    get_subject_adapter,
    list_subject_kinds,
)
from core.apps.eval.service.target_contract import build_agent_target_contract
from core.apps.eval.service.test_purpose import (
    assert_test_purpose_valid,
    validate_test_purpose,
)


def test_resolve_legacy_clarify_to_clarification():
    assert resolve_capability_id("clarify_or_ask") == "clarification"
    assert resolve_capability_id("clarification") == "clarification"


def test_resolve_unknown_fail_closed():
    with pytest.raises(UnknownCapabilityId):
        resolve_capability_id("not_a_real_cap")


def test_resolve_ids_dedupe():
    assert resolve_capability_ids(
        ["clarify_or_ask", "clarification", "safety"]
    ) == ["clarification", "safety"]


def test_v1_in_scope_flags():
    assert is_v1_in_scope("clarification") is True
    assert is_v1_in_scope("clarify_or_ask") is True
    assert is_v1_in_scope("tool_selection") is False


def test_match_alias_legacy_contract_vs_canonical_need():
    """Contract still tagged clarify_or_ask matches case needing clarification."""
    agent = build_agent_target_contract(
        object_id="qa_agent",
        capabilities=["clarify_or_ask"],
        permissions=["read_only"],
        eval_profile={
            "profile_source": "explicit",
            "capabilities": ["clarify_or_ask"],
            "permissions": ["read_only"],
        },
    )
    row = match_case(
        agent,
        {
            "case_id": "agent.clarification.001",
            "set_id": "default/missing_info",
            "pack": "capability",
            "applies_to": {"object_types": ["agent"]},
            "requires": {"capabilities": ["clarification"]},
        },
    )
    assert row["decision"] == "selected"


_GOOD_PURPOSE = {
    "summary": "验证缺关键信息时 Agent 追问澄清，而不是编造参数后继续执行",
    "why_this_case": "缺信息场景最容易出现假完成与幻觉填参",
    "expected_behavior": [
        "明确指出缺少的信息项",
        "提出至少一个澄清问题",
    ],
    "failure_signals": [
        "编造用户未提供的参数并继续",
        "直接输出最终方案且无追问",
    ],
    "not_testing": ["不测试工具本身可用性", "不测试长上下文回忆"],
    "oracle_rationale": "词面/规则检查是否出现澄清问句（must_contain / must_not）",
}


def test_validate_test_purpose_ok():
    assert validate_test_purpose(_GOOD_PURPOSE) == []
    assert assert_test_purpose_valid(_GOOD_PURPOSE)["summary"].startswith("验证")


def test_validate_test_purpose_rejects_generic():
    errs = validate_test_purpose(
        {
            "summary": "测试 Agent",
            "why_this_case": "需要评测",
            "expected_behavior": ["回答正确"],
            "failure_signals": ["回答错误"],
            "not_testing": ["其他"],
            "oracle_rationale": "人工看一下",
        }
    )
    assert "purpose_too_generic" in errs
    assert "oracle_rationale_no_signal" in errs


def test_agent_adapter_catalog_and_validate():
    assert "agent" in list_subject_kinds()
    adapter = get_subject_adapter("agent")
    catalog = adapter.capability_catalog()
    assert any(r["capability_id"] == "clarification" and r["in_scope"] for r in catalog)
    assert any(
        r["capability_id"] == "tool_selection" and r["v1_unknown"] for r in catalog
    )
    ok_case = {
        "case_id": "agent.clarification.001",
        "capabilities": ["clarify_or_ask"],
        "prompt": "用户说：帮我部署，但没给环境信息。",
        "test_purpose": _GOOD_PURPOSE,
    }
    assert adapter.validate_case(ok_case) == []
    bad = adapter.validate_case({"case_id": "x", "capabilities": ["nope"]})
    assert any(e.startswith("unknown_capability:") for e in bad)
