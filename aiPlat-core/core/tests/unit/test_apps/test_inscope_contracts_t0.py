"""T0 in-scope contracts — mock tools / session / long-context / runtime map."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.inscope_contracts_t0 import evaluate_t0_inscope_contracts
from core.apps.eval.service.long_context_fixture_schema import (
    validate_case_long_context_fields,
    validate_long_context_fixture,
)
from core.apps.eval.service.mock_tools import (
    load_mock_tool_catalog,
    validate_mock_tool_catalog,
)
from core.apps.eval.service.session_case_schema import (
    validate_session_case_fields,
    validate_session_group_unique_turns,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter
from core.apps.eval.service.tool_eval_runtime_map import (
    assert_mock_not_claimed_as_live,
    validate_tool_backend_runtime,
)


def test_load_default_mock_catalog():
    cat = load_mock_tool_catalog()
    assert cat["schema"] == "eval.mock_tool_catalog.v1"
    assert validate_mock_tool_catalog(cat) == []
    assert len(cat["tools"]) >= 2


def test_mock_catalog_rejects_bad_name():
    errs = validate_mock_tool_catalog(
        {
            "schema": "eval.mock_tool_catalog.v1",
            "catalog_id": "x",
            "version": "0.1.0",
            "tools": [
                {
                    "name": "Bad-Name",
                    "description": "x",
                    "args_schema": {"type": "object"},
                    "result": {},
                    "fail_modes": [],
                }
            ],
        }
    )
    assert any("invalid_name" in e for e in errs)


def test_session_fields_ok_and_require_group():
    assert validate_session_case_fields(
        {
            "session_group": "g1",
            "turn_index": 0,
            "memory_probe": {
                "planted_fact": "fact-A",
                "ask_after_turns": 1,
                "must_recall": ["fact-A"],
            },
        }
    ) == []
    assert "turn_index_requires_session_group" in validate_session_case_fields(
        {"turn_index": 1}
    )


def test_session_group_unique_turns():
    errs = validate_session_group_unique_turns(
        [
            {"session_group": "g", "turn_index": 0},
            {"session_group": "g", "turn_index": 0},
        ]
    )
    assert "duplicate_turn_index:g" in errs


def test_long_context_fixture_sample():
    path = (
        default_seed_dir()
        / "fixtures"
        / "long_context"
        / "fixture.sample.json"
    )
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert validate_long_context_fixture(fixture) == []
    assert "missing_field:long_context_fixture" in validate_case_long_context_fields(
        {"capabilities": ["long_context"]}
    )


def test_runtime_map_mock_vs_live():
    assert validate_tool_backend_runtime(
        tool_backend="mock", runtime_tier="workspace_execute"
    ) == []
    assert "tool_backend_runtime_mismatch" in validate_tool_backend_runtime(
        tool_backend="mock", runtime_tier="pi"
    )
    assert "mock_claimed_as_live" in assert_mock_not_claimed_as_live(
        tool_backend="mock", runtime_claim_reason="生产工具已测"
    )


def test_evaluate_t0_ok():
    report = evaluate_t0_inscope_contracts()
    assert report["ok"] is True
    assert report["v1_in_scope_unchanged"] is True
    assert all(c["ok"] for c in report["checks"])


def test_adapter_wires_session_validation():
    adapter = get_subject_adapter("agent")
    errs = adapter.validate_case(
        {
            "case_id": "x",
            "capabilities": ["clarification"],
            "turn_index": 0,
            "test_purpose": {
                "summary": "验证缺关键信息时 Agent 追问澄清而不是编造",
                "why_this_case": "字段门",
                "expected_behavior": ["提出澄清问题"],
                "failure_signals": ["编造参数继续"],
                "not_testing": ["不测工具"],
                "oracle_rationale": "must_contain 澄清问句",
            },
        }
    )
    assert "turn_index_requires_session_group" in errs
