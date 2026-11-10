"""WorkflowSubjectAdapter + workflow.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.subject_adapter import (
    WORKFLOW_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)
from core.apps.eval.service.workflow_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_workflow_capability_cases,
    run_workflow_capability_smoke,
    validate_workflow_capability_bank,
    workflow_regression_profile,
    workflow_regression_status,
)

_PURPOSE = {
    "summary": "验证工作流基础阶段序可被正确复述，而不是漏阶段或乱序",
    "why_this_case": "阶段 id 漏写/乱序是 workflow 最小交付最常见失败",
    "expected_behavior": [
        "输出包含 clarify/plan/execute 三词",
        "保持可识别的阶段序",
    ],
    "failure_signals": [
        "缺少任一阶段 id",
        "用中文阶段名替代且无英文 id",
    ],
    "not_testing": ["不测试真实 PipelineEngine 调度", "不测试工具调用"],
    "oracle_rationale": "词面 must_contain 三阶段英文 id",
}


def test_workflow_registered():
    kinds = list_subject_kinds()
    assert "workflow" in kinds
    assert "prompt" in kinds
    assert "agent" in kinds


def test_workflow_catalog_and_roundtrip():
    adapter = get_subject_adapter("workflow")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(WORKFLOW_V1_CAPS)
    case = {
        "case_id": "workflow.task_completion.ut",
        "capabilities": ["task_completion"],
        "prompt": "clarify plan execute",
        "success_criteria": {"must_contain": ["clarify", "plan", "execute"]},
        "scripted_answer": "clarify → plan → execute",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False


def test_workflow_rejects_prompt_only_cap():
    adapter = get_subject_adapter("workflow")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["long_context"],
            "prompt": "long",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("workflow_cap_out_of_scope:") for e in errs)


def test_workflow_seed_bank_smokes():
    report = validate_workflow_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_workflow_capability_cases()
    smoke = run_workflow_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_workflow_regression_profile_and_status():
    prof = workflow_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(WORKFLOW_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = workflow_regression_status()
    assert st["schema"] == "eval.workflow_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 30
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["draft_pending"] == st["case_count"]


def test_eval_workflow_regression_status_facade():
    from core.api.core_facade import (
        eval_workflow_regression_profile,
        eval_workflow_regression_status,
    )

    assert eval_workflow_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_workflow_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
