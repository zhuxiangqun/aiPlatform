"""SystemSubjectAdapter + system.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.system_capability_bank import (
    PROFILE_ID_REGRESSION,
    system_regression_profile,
    system_regression_status,
    build_system_capability_cases,
    run_system_capability_smoke,
    validate_system_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    SYSTEM_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证 system_plan 输出含 status 锚点",
    "why_this_case": "System fixture 最小交付是 lexical 可观测",
    "expected_behavior": ["点名 status", "不假完成"],
    "failure_signals": ["组合失败"],
    "not_testing": ["不测 system_plan_ops 真值"],
    "oracle_rationale": "词面 must_contain",
}


def test_system_registered():
    kinds = list_subject_kinds()
    assert "system" in kinds
    assert "dataset" in kinds


def test_system_catalog_and_roundtrip():
    adapter = get_subject_adapter("system")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(SYSTEM_V1_CAPS)
    case = {
        "case_id": "system.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "system_plan",
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
    contract = adapter.build_contract(object_id="system_under_test")
    assert contract.get("object_type") == "system" or contract.get("claim_eligible") is False


def test_system_rejects_tool_only_cap():
    adapter = get_subject_adapter("system")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("system_cap_out_of_scope:") for e in errs)


def test_system_seed_bank_smokes():
    report = validate_system_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_system_capability_cases()
    smoke = run_system_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_system_regression_profile_and_status():
    prof = system_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(SYSTEM_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = system_regression_status()
    assert st["schema"] == "eval.system_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is True  # pack.meta frozen; claim still closed


def test_eval_system_regression_status_facade():
    from core.api.core_facade import (
        eval_system_regression_profile,
        eval_system_regression_status,
    )

    assert eval_system_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_system_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
