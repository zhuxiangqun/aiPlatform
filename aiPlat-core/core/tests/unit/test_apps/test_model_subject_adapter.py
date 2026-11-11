"""ModelSubjectAdapter + model.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.model_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_model_capability_cases,
    model_regression_profile,
    model_regression_status,
    run_model_capability_smoke,
    validate_model_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    MODEL_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证基础算术问答能保留正确数字锚点，而不是空答或胡说",
    "why_this_case": "模型最小交付最常见失败是漏数字或格式漂移",
    "expected_behavior": [
        "输出包含数字 8",
        "不附加无关长文掩盖答案",
    ],
    "failure_signals": [
        "输出缺 8",
        "输出其它算术结果",
    ],
    "not_testing": ["不测试真实模型 host", "不测试 token 计费"],
    "oracle_rationale": "词面 must_contain 8",
}


def test_model_registered():
    kinds = list_subject_kinds()
    assert "model" in kinds
    assert "workflow" in kinds
    assert "prompt" in kinds
    assert "agent" in kinds


def test_model_catalog_and_roundtrip():
    adapter = get_subject_adapter("model")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(MODEL_V1_CAPS)
    case = {
        "case_id": "model.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "只输出数字：3+5=?",
        "success_criteria": {"must_contain": ["8"]},
        "scripted_answer": "8",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False


def test_model_rejects_workflow_only_cap():
    adapter = get_subject_adapter("model")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["error_recovery"],
            "prompt": "recover",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("model_cap_out_of_scope:") for e in errs)


def test_model_seed_bank_smokes():
    report = validate_model_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_model_capability_cases()
    smoke = run_model_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_model_regression_profile_and_status():
    prof = model_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(MODEL_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = model_regression_status()
    assert st["schema"] == "eval.model_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["case_count"] >= 20
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is True  # pack.meta frozen; claim still closed


def test_eval_model_regression_status_facade():
    from core.api.core_facade import (
        eval_model_regression_profile,
        eval_model_regression_status,
    )

    assert eval_model_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_model_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
