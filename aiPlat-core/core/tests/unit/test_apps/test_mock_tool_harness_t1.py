"""T1 mock tool harness + A3/A4 judge + fixture suite."""
from __future__ import annotations

from core.apps.eval.service.mock_tools import (
    allowed_tool_names,
    invoke_mock_tools,
    load_mock_tool_catalog,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter
from core.apps.eval.service.tool_capability_fixtures import (
    load_tool_capability_fixture_cases,
    run_tool_fixture_suite,
)
from core.apps.eval.service.tool_trace_judge import (
    judge_tool_args,
    judge_tool_selection,
)


def test_allowed_tools_respect_expected_and_forbidden():
    cat = load_mock_tool_catalog()
    allowed = allowed_tool_names(
        {
            "expected_tools": ["echo"],
            "forbidden_tools": ["lookup_fact"],
        },
        catalog=cat,
    )
    assert allowed == {"echo"}


def test_invoke_echo_ok():
    cat = load_mock_tool_catalog()
    out = invoke_mock_tools(
        [{"name": "echo", "args": {"text": "hi"}}],
        case={"expected_tools": ["echo"], "forbidden_tools": []},
        catalog=cat,
    )
    assert out["ok"] is True
    assert out["tool_backend"] == "mock"
    assert out["tool_results"][0]["result"]["echo"] == "hi"


def test_invoke_rejects_forbidden():
    cat = load_mock_tool_catalog()
    out = invoke_mock_tools(
        [{"name": "lookup_fact", "args": {"key": "alpha"}}],
        case={"expected_tools": ["echo"], "forbidden_tools": ["lookup_fact"]},
        catalog=cat,
    )
    assert out["ok"] is False
    assert any("tool_not_allowed" in e for e in out["errors"])


def test_judge_selection_pos_neg():
    pos = judge_tool_selection(
        {"expected_tools": ["echo"], "forbidden_tools": ["lookup_fact"], "exact_tool_set": True},
        {"tool_calls": [{"name": "echo", "args": {"text": "a"}}]},
    )
    assert pos["passed"] is True
    neg = judge_tool_selection(
        {"expected_tools": ["echo"], "forbidden_tools": ["lookup_fact"]},
        {
            "tool_calls": [
                {"name": "echo", "args": {"text": "a"}},
                {"name": "lookup_fact", "args": {"key": "alpha"}},
            ]
        },
    )
    assert neg["passed"] is False
    assert any("forbidden_tool_used" in e for e in neg["errors"])


def test_judge_args_pos_neg():
    pos = judge_tool_args(
        {"expected_tool_args": {"echo": {"text": "ok"}}},
        {"tool_calls": [{"name": "echo", "args": {"text": "ok"}}]},
    )
    assert pos["passed"] is True
    neg = judge_tool_args(
        {},
        {"tool_calls": [{"name": "echo", "args": {}}]},
    )
    assert neg["passed"] is False


def test_adapter_execute_judge_normalize_tool_path():
    adapter = get_subject_adapter("agent")
    case = {
        "case_id": "x",
        "capabilities": ["tool_selection", "tool_args"],
        "expected_tools": ["echo"],
        "forbidden_tools": [],
        "scripted_tool_calls": [{"name": "echo", "args": {"text": "z"}}],
        "test_purpose": {
            "summary": "验证工具路径 execute/judge 接线",
            "why_this_case": "unit",
            "expected_behavior": ["调用 echo"],
            "failure_signals": ["未调用"],
            "not_testing": ["不测 session"],
            "oracle_rationale": "tool_trace must_contain echo",
        },
    }
    exe = adapter.execute(case)
    assert exe["status"] == "ok"
    assert exe["tool_backend"] == "mock"
    j = adapter.judge(case, exe)
    assert j["passed"] is True
    n = adapter.normalize(case, exe, j)
    assert n["passed"] is True
    assert n["claim_eligible"] is False
    assert n["v1_in_scope"] is True  # v1.1 measurable subset (mock ≠ claim)


def test_fixture_suite_has_five_each_and_passes():
    a3 = load_tool_capability_fixture_cases(capability_id="tool_selection")
    a4 = load_tool_capability_fixture_cases(capability_id="tool_args")
    assert len(a3) >= 5
    assert len(a4) >= 5
    report = run_tool_fixture_suite()
    assert report["n_cases"] >= 10
    assert report["ok"] is True, report
    assert report["claim_eligible"] is False
