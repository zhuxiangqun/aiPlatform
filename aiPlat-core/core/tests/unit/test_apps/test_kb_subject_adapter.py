"""KbSubjectAdapter + kb.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.kb_capability_bank import (
    PROFILE_ID_REGRESSION,
    build_kb_capability_cases,
    kb_regression_profile,
    kb_regression_status,
    run_kb_capability_smoke,
    validate_kb_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    KB_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证受控 hits 覆盖 expected_ids",
    "why_this_case": "KB fixture 最小交付是 expected 命中",
    "expected_behavior": ["hits 含金标 id"],
    "failure_signals": ["hits 为空", "expected 未覆盖"],
    "not_testing": ["不测试 live 检索"],
    "oracle_rationale": "规则 oracle：expected_ids 全部命中",
}


def test_kb_registered():
    kinds = list_subject_kinds()
    assert "kb" in kinds
    assert "model" in kinds
    assert "workflow" in kinds
    assert "prompt" in kinds
    assert "agent" in kinds


def test_kb_catalog_and_roundtrip():
    adapter = get_subject_adapter("kb")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(KB_V1_CAPS)
    case = {
        "case_id": "kb.task_completion.ut",
        "capabilities": ["task_completion"],
        "query": "什么是缺陷门禁？",
        "hits": [{"id": "d1", "text": "缺陷门禁要求零发现回执。"}],
        "expected_ids": ["d1"],
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="kb.fixture")
    assert contract["object_type_registered"] is False
    assert contract["claim_eligible"] is False


def test_kb_empty_hits_fail_closed():
    adapter = get_subject_adapter("kb")
    case = {
        "case_id": "kb.empty",
        "capabilities": ["task_completion"],
        "query": "无召回",
        "hits": [],
        "test_purpose": _PURPOSE,
    }
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    assert judgment["passed"] is False
    assert "missing_hits" in judgment["errors"]


def test_kb_rejects_workflow_only_cap():
    adapter = get_subject_adapter("kb")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["error_recovery"],
            "query": "recover",
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("kb_cap_out_of_scope:") for e in errs)


def test_kb_seed_bank_smokes():
    report = validate_kb_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 15
    assert build_kb_capability_cases()
    smoke = run_kb_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False


def test_kb_regression_profile_and_status():
    prof = kb_regression_profile()
    assert prof["profile_id"] == PROFILE_ID_REGRESSION
    assert prof["claim_eligible"] is False
    assert set(prof["quotas"]) == set(KB_V1_CAPS)
    assert all(int(v) >= 5 for v in prof["quotas"].values())

    st = kb_regression_status()
    assert st["schema"] == "eval.kb_regression_status.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["case_count"] >= 15
    assert st["claim_eligible"] is False
    assert st["accuracy_claim"] is False
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["profile_complete"] is False  # pack.meta still draft; claim closed


def test_eval_kb_regression_status_facade():
    from core.api.core_facade import (
        eval_kb_regression_profile,
        eval_kb_regression_status,
    )

    assert eval_kb_regression_profile()["profile_id"] == PROFILE_ID_REGRESSION
    st = eval_kb_regression_status()
    assert st["quota_inventory_ok"] is True
    assert st["certification_eligible"] is False
