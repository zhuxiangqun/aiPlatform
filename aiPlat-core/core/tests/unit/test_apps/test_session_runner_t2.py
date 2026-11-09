"""T2 A5 tool_result_use + session runner / A8 fixtures."""
from __future__ import annotations

import pytest

from core.apps.eval.service.session_runner import (
    SessionRunnerError,
    assert_session_groups_complete,
    run_session_group,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter
from core.apps.eval.service.tool_capability_fixtures import (
    load_session_fixture_cases,
    load_tool_capability_fixture_cases,
    run_session_fixture_suite,
    run_tool_fixture_suite,
)
from core.apps.eval.service.tool_trace_judge import judge_tool_result_use


def test_judge_tool_result_use_pos_neg():
    pos = judge_tool_result_use(
        {"must_contain_from_tools": ["42"]},
        {
            "answer": "值为 42",
            "tool_results": [{"ok": True, "result": {"value": "42"}}],
        },
    )
    assert pos["passed"] is True
    neg = judge_tool_result_use(
        {"must_contain_from_tools": ["42"]},
        {"answer": "不知道", "tool_results": []},
    )
    assert neg["passed"] is False


def test_a5_fixture_cases_and_suite():
    a5 = load_tool_capability_fixture_cases(capability_id="tool_result_use")
    assert len(a5) >= 5
    report = run_tool_fixture_suite(capability_id="tool_result_use")
    assert report["ok"] is True, report


def test_full_tool_suite_includes_a5():
    report = run_tool_fixture_suite()
    assert report["n_cases"] >= 15
    assert report["ok"] is True, report


def test_session_group_split_fail_closed():
    uni = [
        {"case_id": "a", "session_group": "g", "turn_index": 0},
        {"case_id": "b", "session_group": "g", "turn_index": 1},
    ]
    with pytest.raises(SessionRunnerError, match="session_group_split"):
        assert_session_groups_complete([uni[0]], uni)


def test_session_runner_recall():
    cases = [
        {
            "case_id": "t0",
            "session_group": "g",
            "turn_index": 0,
            "memory_probe": {
                "planted_fact": "X",
                "ask_after_turns": 1,
                "must_recall": ["TOKEN"],
            },
            "scripted_answer": "ok",
        },
        {
            "case_id": "t1",
            "session_group": "g",
            "turn_index": 1,
            "scripted_answer": "TOKEN here",
        },
    ]
    rep = run_session_group(cases)
    assert rep["ok"] is True


def test_session_fixture_suite():
    cases = load_session_fixture_cases()
    assert len(cases) >= 5
    report = run_session_fixture_suite()
    assert report["ok"] is True, report
    assert report["claim_eligible"] is False


def test_adapter_a5_path():
    adapter = get_subject_adapter("agent")
    case = {
        "capabilities": ["tool_result_use"],
        "expected_tools": ["lookup_fact"],
        "scripted_tool_calls": [{"name": "lookup_fact", "args": {"key": "alpha"}}],
        "scripted_answer": "值为 42",
        "must_contain_from_tools": ["42"],
        "test_purpose": {
            "summary": "验证工具结果进入最终回答",
            "why_this_case": "unit",
            "expected_behavior": ["含 42"],
            "failure_signals": ["缺失"],
            "not_testing": ["不测 session"],
            "oracle_rationale": "must_contain_from_tools",
        },
    }
    exe = adapter.execute(case)
    assert exe["status"] == "ok"
    j = adapter.judge(case, exe)
    assert j["passed"] is True
