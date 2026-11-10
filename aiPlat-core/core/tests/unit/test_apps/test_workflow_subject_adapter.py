"""WorkflowSubjectAdapter + workflow.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.subject_adapter import (
    WORKFLOW_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)
from core.apps.eval.service.workflow_capability_bank import (
    build_workflow_capability_cases,
    run_workflow_capability_smoke,
    validate_workflow_capability_bank,
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
    assert report["case_count"] >= 3
    assert build_workflow_capability_cases()
    smoke = run_workflow_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False
