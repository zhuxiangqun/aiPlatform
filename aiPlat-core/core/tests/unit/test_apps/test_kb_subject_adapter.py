"""KbSubjectAdapter + kb.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.kb_capability_bank import (
    build_kb_capability_cases,
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
    assert report["case_count"] >= 3
    assert build_kb_capability_cases()
    smoke = run_kb_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False
