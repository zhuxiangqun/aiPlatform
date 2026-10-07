"""Stage reflection closure — deterministic path (no LLM)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.harness.execution.stage_reflection import (
    build_stage_reflection,
    capture_stage_reflection,
)


def test_build_reflection_from_health_report():
    stage = SimpleNamespace(id="s1", agent_id="coder", output_artifact="code")
    state = {
        "_health_report_s1": {
            "verdict": "passed",
            "overall_score": 82,
            "dimensions": [
                {"name": "correctness", "score": 8.0},
                {"name": "style", "score": 4.0},
            ],
        },
        "code": "## FILE: a.py\nprint(1)",
    }
    ref = build_stage_reflection(stage, state)
    assert ref["verdict"] == "passed"
    assert ref["agent_id"] == "coder"
    assert any("overall_score" in s for s in ref["strengths"])
    assert any("style" in p for p in ref["problems"])
    assert ref["lesson"]
    assert ref["source"] == "deterministic"
    assert "timestamp" in ref


def test_build_reflection_failed_on_error():
    stage = SimpleNamespace(id="s2", agent_id="qa", output_artifact="report")
    state = {"error": "token_budget_exhausted"}
    ref = build_stage_reflection(stage, state)
    assert ref["verdict"] == "failed"
    assert "token_budget_exhausted" in ref["problems"][0]


def test_capture_stage_reflection_async_no_llm(monkeypatch):
    monkeypatch.delenv("AIPLAT_STAGE_REFLECTION_LLM", raising=False)
    stage = SimpleNamespace(id="s3", agent_id="pm", output_artifact="prd")
    state = {"prd": {"title": "x"}}
    ref = asyncio.get_event_loop().run_until_complete(capture_stage_reflection(stage, state))
    assert ref["verdict"] == "passed"
    assert ref["source"] == "deterministic"
