"""SkillSubjectAdapter + skill.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.skill_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_skill_capability_cases,
    run_skill_capability_smoke,
    skill_regression_profile,
    skill_regression_status,
    validate_skill_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    SKILL_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证 skill 触发输出含技能名锚点",
    "why_this_case": "Skill fixture 最小交付是 lexical invoke 可观测",
    "expected_behavior": ["点名技能", "不假完成"],
    "failure_signals": ["未调用"],
    "not_testing": ["不测 live handler"],
    "oracle_rationale": "词面 must_contain",
}


def test_skill_registered():
    kinds = list_subject_kinds()
    assert "skill" in kinds
    assert "prompt" in kinds
    assert "multi_agent" in kinds


def test_skill_catalog_and_roundtrip():
    adapter = get_subject_adapter("skill")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(SKILL_V1_CAPS)
    case = {
        "case_id": "skill.task_completion.ut",
        "capabilities": ["skill_invoke"],
        "prompt": "调用 summarize_doc",
        "success_criteria": {"must_contain": ["summarize_doc"]},
        "scripted_answer": "已调用 summarize_doc",
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="skill.fixture")
    assert contract.get("object_type") == "skill" or contract.get("claim_eligible") is False
    assert normalized["passed"] is True


def test_skill_rejects_tool_only_cap():
    adapter = get_subject_adapter("skill")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["tool_selection"],
            "prompt": "tools",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("skill_cap_out_of_scope:") for e in errs)


def test_skill_seed_bank_smokes():
    report = validate_skill_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_skill_capability_cases()
    smoke = run_skill_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_skill_regression_profile_and_status():
    prof = skill_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(SKILL_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = skill_regression_status()
    assert st["schema"] == "eval.skill_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["draft_pending"] == st["case_count"]


def test_eval_skill_regression_status_facade():
    from core.api.core_facade import (
        eval_skill_regression_profile,
        eval_skill_regression_status,
    )

    assert eval_skill_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_skill_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
