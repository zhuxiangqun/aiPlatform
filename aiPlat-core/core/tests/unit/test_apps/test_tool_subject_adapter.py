"""ToolSubjectAdapter + tool.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.subject_adapter import (
    TOOL_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)
from core.apps.eval.service.tool_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_tool_capability_cases,
    run_tool_capability_smoke,
    tool_regression_profile,
    tool_regression_status,
    validate_tool_capability_bank,
)

_PURPOSE = {
    "summary": "验证仅选择 echo 完成回显",
    "why_this_case": "Tool Subject A3 正例",
    "expected_behavior": ["调用 echo"],
    "failure_signals": ["漏调 echo"],
    "not_testing": ["不测 live MCP"],
    "oracle_rationale": "规则 oracle：tool_trace expected/forbidden",
}


def test_tool_registered():
    kinds = list_subject_kinds()
    assert "tool" in kinds
    assert "session" in kinds
    assert "agent" in kinds


def test_tool_catalog_and_roundtrip():
    adapter = get_subject_adapter("tool")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(TOOL_V1_CAPS)
    case = {
        "case_id": "tool.tool_selection.ut",
        "capabilities": ["tool_selection"],
        "prompt": "echo hi",
        "expected_tools": ["echo"],
        "forbidden_tools": ["lookup_fact"],
        "exact_tool_set": True,
        "scripted_tool_calls": [{"name": "echo", "args": {"text": "hi"}}],
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert result["status"] == "ok"
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="tool.fixture")
    assert contract["object_type_registered"] is False
    assert contract["claim_eligible"] is False


def test_tool_forbidden_fail_closed():
    adapter = get_subject_adapter("tool")
    case = {
        "case_id": "tool.forbidden",
        "capabilities": ["tool_selection"],
        "prompt": "should not lookup",
        "expected_tools": ["echo"],
        "forbidden_tools": ["lookup_fact"],
        "exact_tool_set": True,
        "scripted_tool_calls": [
            {"name": "echo", "args": {"text": "x"}},
            {"name": "lookup_fact", "args": {"key": "alpha"}},
        ],
        "test_purpose": _PURPOSE,
    }
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    assert judgment["passed"] is False
    assert any(str(e).startswith("forbidden_tool_used:") for e in judgment["errors"])


def test_tool_rejects_session_only_cap():
    adapter = get_subject_adapter("tool")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["multi_turn_memory"],
            "prompt": "remember",
            "scripted_tool_calls": [{"name": "echo", "args": {"text": "x"}}],
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("tool_cap_out_of_scope:") for e in errs)


def test_tool_seed_bank_smokes():
    report = validate_tool_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_tool_capability_cases()
    smoke = run_tool_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_tool_regression_profile_and_status():
    prof = tool_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(TOOL_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = tool_regression_status()
    assert st["schema"] == "eval.tool_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is True  # pack.meta frozen; claim still closed


def test_eval_tool_regression_status_facade():
    from core.api.core_facade import (
        eval_tool_regression_profile,
        eval_tool_regression_status,
    )

    assert eval_tool_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_tool_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
