"""GeneratedAppSubjectAdapter + generated_app.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.generated_app_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_generated_app_capability_cases,
    generated_app_regression_profile,
    generated_app_regression_status,
    run_generated_app_capability_smoke,
    validate_generated_app_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    GENERATED_APP_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证生成应用导出输出含交付锚点",
    "why_this_case": "Generated-App fixture 最小交付是 lexical 可观测",
    "expected_behavior": ["点名交付物", "不假完成"],
    "failure_signals": ["导出失败"],
    "not_testing": ["不测 live Pi"],
    "oracle_rationale": "词面 must_contain",
}


def test_generated_app_registered():
    kinds = list_subject_kinds()
    assert "generated_app" in kinds
    assert "skill" in kinds


def test_generated_app_catalog_and_roundtrip():
    adapter = get_subject_adapter("generated_app")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(GENERATED_APP_V1_CAPS)
    case = {
        "case_id": "generated_app.task_completion.ut",
        "capabilities": ["pi_export"],
        "prompt": "export pi package",
        "success_criteria": {"must_contain": ["manifest"]},
        "scripted_answer": "manifest ready",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="generated_app.fixture")
    assert contract.get("object_type") == "generated_app" or contract.get("claim_eligible") is False


def test_generated_app_rejects_tool_only_cap():
    adapter = get_subject_adapter("generated_app")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("generated_app_cap_out_of_scope:") for e in errs)


def test_generated_app_seed_bank_smokes():
    report = validate_generated_app_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_generated_app_capability_cases()
    smoke = run_generated_app_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_generated_app_regression_profile_and_status():
    prof = generated_app_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(GENERATED_APP_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = generated_app_regression_status()
    assert st["schema"] == "eval.generated_app_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is False  # pack.meta still draft; claim closed


def test_eval_generated_app_regression_status_facade():
    from core.api.core_facade import (
        eval_generated_app_regression_profile,
        eval_generated_app_regression_status,
    )

    assert eval_generated_app_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_generated_app_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
