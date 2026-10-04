"""StageRunner must copy AGENT preferred_language into LoopState.context."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_stage_runner_propagates_preferred_language(monkeypatch):
    from core.harness.execution.langgraph.stage_runner import StageRunner
    from core.harness.interfaces.loop import LoopState

    captured: dict = {}

    class _FakeLoop:
        def __init__(self, *a, **k):
            pass

        async def run(self, loop_state: LoopState, config=None):
            captured["preferred"] = loop_state.context.get("_preferred_language")
            captured["user_task"] = loop_state.context.get("_user_task")

            class _Result:
                final_state = loop_state
                final_answer = "ok"
                success = True
                output = "ok"

            return _Result()

    monkeypatch.setattr(
        "core.harness.execution.langgraph.stage_runner.ReActLoop",
        _FakeLoop,
    )

    class _Cfg:
        max_steps_per_stage = 3
        max_tokens_per_run = 100000
        stages = []

    runner = StageRunner(model=object(), tools=[], skills=[], pipeline_config=_Cfg())
    # StageRunner.run(prompt, state, stage=None, tools=None) — max_steps comes from config
    await runner.run(
        "ignored wrapper",
        {
            "session_id": "s1",
            "_run_id": "run-test",
            "_user_task": "生成报障列表页切片",
            "_preferred_language": "typescript",
            "_skill_delivery": "once",
            "_sys_prompt": "you are FE",
            "context": {"task": "生成报障列表页切片", "system_prompt": "you are FE"},
        },
    )
    assert captured.get("preferred") == "typescript"
    assert "报障" in str(captured.get("user_task") or "")
