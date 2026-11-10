"""MultiAgentSubjectAdapter + multi_agent.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.multi_agent_capability_bank import (
    build_multi_agent_capability_cases,
    run_multi_agent_capability_smoke,
    validate_multi_agent_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    MULTI_AGENT_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证协作路径精确匹配",
    "why_this_case": "Multi-Agent fixture 最小交付是 path exact",
    "expected_behavior": ["handoff 边序列 exact"],
    "failure_signals": ["路径漂移"],
    "not_testing": ["不测 live runtime"],
    "oracle_rationale": "规则 oracle：handoff_path exact",
}


def test_multi_agent_registered():
    kinds = list_subject_kinds()
    assert "multi_agent" in kinds
    assert "tool" in kinds
    assert "session" in kinds


def test_multi_agent_catalog_and_roundtrip():
    adapter = get_subject_adapter("multi_agent")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(MULTI_AGENT_V1_CAPS)
    case = {
        "case_id": "multi_agent.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "coord -> worker",
        "handoffs": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},
        ],
        "expected_handoff_path": [["a", "b"], ["b", "a"]],
        "final_answer": "done",
        "expected_final": "done",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="multi_agent.fixture")
    assert contract["object_type_registered"] is False
    assert contract["claim_eligible"] is False


def test_multi_agent_path_mismatch_fail_closed():
    adapter = get_subject_adapter("multi_agent")
    case = {
        "case_id": "multi_agent.mismatch",
        "capabilities": ["task_completion"],
        "prompt": "wrong path",
        "handoffs": [{"from": "a", "to": "c"}],
        "expected_handoff_path": [["a", "b"]],
        "final_answer": "x",
        "expected_final": "x",
        "test_purpose": _PURPOSE,
    }
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    assert judgment["passed"] is False
    assert "handoff_path_mismatch" in judgment["errors"]


def test_multi_agent_rejects_tool_only_cap():
    adapter = get_subject_adapter("multi_agent")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "handoffs": [{"from": "a", "to": "b"}],
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("multi_agent_cap_out_of_scope:") for e in errs)


def test_multi_agent_seed_bank_smokes():
    report = validate_multi_agent_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 3
    assert build_multi_agent_capability_cases()
    smoke = run_multi_agent_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False
