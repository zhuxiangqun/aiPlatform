"""CodeReviewSubjectAdapter + code_review.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.code_review_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_code_review_capability_cases,
    code_review_regression_profile,
    code_review_regression_status,
    run_code_review_capability_smoke,
    validate_code_review_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    CODE_REVIEW_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证 findings 与 gold 精确集合相等",
    "why_this_case": "Code Review fixture 最小交付是 exact set match",
    "expected_behavior": ["集合相等"],
    "failure_signals": ["缺 gold", "集合不等"],
    "not_testing": ["不测试 live autoreview"],
    "oracle_rationale": "规则 oracle：sorted(str(findings)) == sorted(str(gold))",
}


def test_code_review_registered():
    kinds = list_subject_kinds()
    assert "code_review" in kinds
    assert "kb" in kinds
    assert "model" in kinds


def test_code_review_catalog_and_roundtrip():
    adapter = get_subject_adapter("code_review")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(CODE_REVIEW_V1_CAPS)
    case = {
        "case_id": "code_review.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "mark sql injection",
        "findings": ["a:1:P0:sql"],
        "gold": ["a:1:P0:sql"],
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert judgment["exact_set_match"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="cr.fixture")
    assert contract["object_type_registered"] is False


def test_code_review_missing_gold_fail_closed():
    adapter = get_subject_adapter("code_review")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["task_completion"],
            "prompt": "review",
            "findings": ["a"],
            "test_purpose": _PURPOSE,
        }
    )
    assert "missing_field:gold" in errs
    result = adapter.execute(
        {
            "case_id": "x",
            "capabilities": ["task_completion"],
            "prompt": "review",
            "findings": ["a"],
            "gold": [],
            "test_purpose": _PURPOSE,
        }
    )
    judgment = adapter.judge({"gold": []}, result)
    assert judgment["passed"] is False
    assert "missing_gold" in judgment["errors"]


def test_code_review_rejects_kb_only_cap():
    adapter = get_subject_adapter("code_review")
    # long_context is in agent/prompt but out of code_review v1
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["long_context"],
            "prompt": "review",
            "gold": ["a"],
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("code_review_cap_out_of_scope:") for e in errs)


def test_code_review_seed_bank_smokes():
    report = validate_code_review_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_code_review_capability_cases()
    smoke = run_code_review_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_code_review_regression_profile_and_status():
    prof = code_review_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(CODE_REVIEW_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = code_review_regression_status()
    assert st["schema"] == "eval.code_review_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is True  # pack.meta frozen; claim still closed


def test_eval_code_review_regression_status_facade():
    from core.api.core_facade import (
        eval_code_review_regression_profile,
        eval_code_review_regression_status,
    )

    assert eval_code_review_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_code_review_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
