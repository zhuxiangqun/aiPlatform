"""MultiAgentSubjectAdapter + multi_agent.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.multi_agent_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_multi_agent_capability_cases,
    multi_agent_regression_profile,
    multi_agent_regression_status,
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
    assert report["case_count"] >= 15
    assert build_multi_agent_capability_cases()
    smoke = run_multi_agent_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_multi_agent_regression_profile_and_status():
    prof = multi_agent_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(MULTI_AGENT_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = multi_agent_regression_status()
    assert st["schema"] == "eval.multi_agent_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is False  # pack.meta still draft; claim closed


def test_eval_multi_agent_regression_status_facade():
    from core.api.core_facade import (
        eval_multi_agent_regression_profile,
        eval_multi_agent_regression_status,
    )

    assert eval_multi_agent_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_multi_agent_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
