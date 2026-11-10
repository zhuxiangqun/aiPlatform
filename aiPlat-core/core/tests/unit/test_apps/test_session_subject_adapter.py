"""SessionSubjectAdapter + session.capability seed bank."""
from __future__ import annotations

from core.apps.eval.service.session_capability_bank import (
    build_session_capability_cases,
    run_session_capability_smoke,
    validate_session_capability_bank,
)
from core.apps.eval.service.subject_adapter import (
    SESSION_V1_CAPS,
    get_subject_adapter,
    list_subject_kinds,
)

_PURPOSE = {
    "summary": "验证两轮 fixture 按 expected 精确匹配",
    "why_this_case": "Session fixture 最小交付是多轮 exact",
    "expected_behavior": ["两轮均 exact"],
    "failure_signals": ["轮次不足", "exact 失败"],
    "not_testing": ["不测试长程记忆"],
    "oracle_rationale": "规则 oracle：profile 内全轮 exact",
}


def test_session_registered():
    kinds = list_subject_kinds()
    assert "session" in kinds
    assert "code_review" in kinds
    assert "kb" in kinds


def test_session_catalog_and_roundtrip():
    adapter = get_subject_adapter("session")
    ids = {r["capability_id"] for r in adapter.capability_catalog()}
    assert ids == set(SESSION_V1_CAPS)
    case = {
        "case_id": "session.task_completion.ut",
        "capabilities": ["task_completion"],
        "profile": "v0",
        "turns": [
            {"prompt": "hi", "expected": "hello", "actual": "hello"},
            {"prompt": "again", "expected": "hello2", "actual": "hello2"},
        ],
        "test_purpose": _PURPOSE,
    }
    assert adapter.validate_case(case) == []
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    normalized = adapter.normalize(case, result, judgment)
    assert judgment["passed"] is True
    assert normalized["claim_eligible"] is False
    contract = adapter.build_contract(object_id="session.fixture")
    assert contract["object_type_registered"] is False
    assert contract["claim_eligible"] is False


def test_session_turn_mismatch_fail_closed():
    adapter = get_subject_adapter("session")
    case = {
        "case_id": "session.mismatch",
        "capabilities": ["task_completion"],
        "profile": "v0",
        "turns": [
            {"prompt": "a", "expected": "ok", "actual": "ok"},
            {"prompt": "b", "expected": "yes", "actual": "no"},
        ],
        "test_purpose": _PURPOSE,
    }
    result = adapter.execute(case)
    judgment = adapter.judge(case, result)
    assert judgment["passed"] is False
    assert "turn_failures" in judgment["errors"]


def test_session_rejects_out_of_scope_cap():
    adapter = get_subject_adapter("session")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["safety"],
            "profile": "v0",
            "turns": [
                {"prompt": "a", "expected": "b"},
                {"prompt": "c", "expected": "d"},
            ],
            "test_purpose": _PURPOSE,
        }
    )
    assert any(e.startswith("session_cap_out_of_scope:") for e in errs)


def test_session_seed_bank_smokes():
    report = validate_session_capability_bank()
    assert report["ok"] is True, report.get("errors")
    assert report["case_count"] >= 3
    assert build_session_capability_cases()
    smoke = run_session_capability_smoke()
    assert smoke["ok"] is True, smoke
    assert smoke["claim_eligible"] is False
