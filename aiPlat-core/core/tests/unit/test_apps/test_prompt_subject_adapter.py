"""PromptSubjectAdapter + prompt.capability seed bank (ADR expansion)."""
from __future__ import annotations

from core.apps.eval.service.prompt_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_prompt_capability_cases,
    prompt_regression_profile,
    prompt_regression_status,
    run_prompt_capability_smoke,
    validate_prompt_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    PROMPT_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)


_PURPOSE = {
    "summary": "验证模板变量齐全时输出保留产品名锚点，而不是丢掉关键槽位",
    "why_this_case": "基础 prompt 渲染最常见失败是漏变量或改写丢键",
    "expected_behavior": [
        "输出包含产品名「智能门锁」",
        "不编造未给出的其它产品名",
    ],
    "failure_signals": [
        "输出缺少「智能门锁」",
        "用占位符 {{product}} 原样返回",
    ],
    "not_testing": ["不测试工具调用", "不测试多轮记忆"],
    "oracle_rationale": "词面 must_contain 检查产品名锚点",
}


def test_prompt_registered_alongside_agent():
    kinds = list_subject_kinds()
    assert "agent" in kinds
    assert "prompt" in kinds


def test_prompt_catalog_subset():
    adapter = get_subject_adapter("prompt")
    catalog = adapter.capability_catalog()
    ids = {r["capability_id"] for r in catalog}
    assert ids == set(PROMPT_V1_CAPS)
    assert all(r["object_types"] == ["prompt"] for r in catalog)


def test_prompt_validate_and_execute_judge_normalize():
    adapter = get_subject_adapter("prompt")
    case = {
        "case_id": "prompt.task_completion.ut",
        "capabilities": ["format_constraint"],
        "prompt": "输出产品名智能门锁",
        "success_criteria": {"must_contain": ["智能门锁"]},
        "scripted_answer": "产品：智能门锁",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    assert result["ok"] is True
    assert result["runtime_claim"] is False
    judgment = adapter.judge(case, result)
    assert judgment["passed"] is True
    normalized = adapter.normalize(case, result, judgment)
    assert normalized["claim_eligible"] is False
    assert normalized["passed"] is True


def test_prompt_rejects_agent_only_cap():
    adapter = get_subject_adapter("prompt")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "call a tool",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("prompt_cap_out_of_scope:") for e in errs)


def test_prompt_seed_bank_validates_and_smokes():
    report = validate_prompt_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    cases = build_prompt_capability_cases()
    assert any(c["case_id"].startswith("prompt.") for c in cases)
    smoke = run_prompt_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_prompt_regression_profile_and_status():
    prof = prompt_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(PROMPT_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = prompt_regression_status()
    assert st["schema"] == "eval.prompt_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["case_count"] >= 25
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is True  # pack.meta frozen; claim still closed


def test_eval_prompt_regression_status_facade():
    from core.api.core_facade import (
        eval_prompt_regression_profile,
        eval_prompt_regression_status,
    )

    assert eval_prompt_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_prompt_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
