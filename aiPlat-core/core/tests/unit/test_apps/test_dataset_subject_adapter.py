"""DatasetSubjectAdapter + dataset.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.dataset_capability_bank import (
    PROFILE_ID_REGRESSION,
    dataset_regression_profile,
    dataset_regression_status,
    build_dataset_capability_cases,
    run_dataset_capability_smoke,
    validate_dataset_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    DATASET_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证 fixture_table 输出含 status 锚点",
    "why_this_case": "Dataset fixture 最小交付是 lexical 可观测",
    "expected_behavior": ["点名 status", "不假完成"],
    "failure_signals": ["断言失败"],
    "not_testing": ["不测 typed Plan dataset_assert"],
    "oracle_rationale": "词面 must_contain",
}


def test_dataset_registered():
    kinds = list_subject_kinds()
    assert "dataset" in kinds
    assert "api" in kinds


def test_dataset_catalog_and_roundtrip():
    adapter = get_subject_adapter("dataset")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(DATASET_V1_CAPS)
    case = {
        "case_id": "dataset.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "fixture_table",
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
    assert contract.get("object_type") == "dataset" or contract.get("claim_eligible") is False


def test_dataset_rejects_tool_only_cap():
    adapter = get_subject_adapter("dataset")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("dataset_cap_out_of_scope:") for e in errs)


def test_dataset_seed_bank_smokes():
    report = validate_dataset_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_dataset_capability_cases()
    smoke = run_dataset_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_dataset_regression_profile_and_status():
    prof = dataset_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(DATASET_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = dataset_regression_status()
    assert st["schema"] == "eval.dataset_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["draft_pending"] == st["case_count"]


def test_eval_dataset_regression_status_facade():
    from core.api.core_facade import (
        eval_dataset_regression_profile,
        eval_dataset_regression_status,
    )

    assert eval_dataset_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_dataset_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
