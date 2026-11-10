"""ApiSubjectAdapter + api.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.api_capability_bank import (
    PROFILE_ID_REGRESSION,
    api_regression_profile,
    api_regression_status,
    build_api_capability_cases,
    run_api_capability_smoke,
    validate_api_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    API_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证 chat_pull 输出含 status 锚点",
    "why_this_case": "API fixture 最小交付是 lexical 可观测",
    "expected_behavior": ["点名 status", "不假完成"],
    "failure_signals": ["拉取失败"],
    "not_testing": ["不测 live HTTP"],
    "oracle_rationale": "词面 must_contain",
}


def test_api_registered():
    kinds = list_subject_kinds()
    assert "api" in kinds
    assert "generated_app" in kinds


def test_api_catalog_and_roundtrip():
    adapter = get_subject_adapter("api")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(API_V1_CAPS)
    case = {
        "case_id": "api.task_completion.ut",
        "capabilities": ["http_chat_pull"],
        "prompt": "chat_pull",
        "success_criteria": {"must_contain": ["status=ok"]},
        "scripted_answer": "status=ok",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="ext:demo")
    assert contract.get("object_type") == "api" or contract.get("claim_eligible") is False


def test_api_rejects_tool_only_cap():
    adapter = get_subject_adapter("api")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("api_cap_out_of_scope:") for e in errs)


def test_api_seed_bank_smokes():
    report = validate_api_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_api_capability_cases()
    smoke = run_api_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_api_regression_profile_and_status():
    prof = api_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(API_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = api_regression_status()
    assert st["schema"] == "eval.api_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["draft_pending"] == st["case_count"]


def test_eval_api_regression_status_facade():
    from core.api.core_facade import (
        eval_api_regression_profile,
        eval_api_regression_status,
    )

    assert eval_api_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_api_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
