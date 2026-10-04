"""Self-correct must not nested-LLM after a failed skill Observation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


@pytest.mark.asyncio
async def test_self_correct_skips_skill_error_observation():
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    state = LoopState(current=LoopStateEnum.OBSERVING, context={"_run_id": "run-t"})
    with patch(
        "core.harness.execution.loop._facade.sys_llm_generate",
        new_callable=AsyncMock,
    ) as gen:
        out = await loop._try_self_correct(
            "Skill error: architecture_lone_api: emit full architecture JSON\n"
            "Rejected output (do not treat as final answer):\n"
            "{\"method\":\"POST\",\"path\":\"/api/x\"}",
            state,
        )
    assert out == ""
    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_correct_skips_lone_api_token():
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    state = LoopState(current=LoopStateEnum.OBSERVING, context={})
    with patch(
        "core.harness.execution.loop._facade.sys_llm_generate",
        new_callable=AsyncMock,
    ) as gen:
        out = await loop._try_self_correct(
            "architecture_lone_api: output is a single endpoint",
            state,
        )
    assert out == ""
    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_correct_skips_after_successful_skill_call():
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.OBSERVING,
        context={
            "_run_id": "run-74a19d55326c",
            "skill_call": {"skill": "test_executor", "args": {}},
        },
    )
    report = '{"header":{"report_id":"TR-1"},"meta":{"total_test_cases":0},"test_results":[]}'
    with patch(
        "core.harness.execution.loop._facade.sys_llm_generate",
        new_callable=AsyncMock,
    ) as gen:
        out = await loop._try_self_correct(report, state)
    assert out == ""
    gen.assert_not_awaited()


def test_observe_bound_skill_delivery_wired_in_facade():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[3] / "harness/execution/loop/_facade.py"
    ).read_text(encoding="utf-8")
    assert 'source="observe_bound_skill_delivery"' in src
    assert "skill_call" in src and "_primary_skill_delivered" in src
    assert "test_executor JSON report is not a code stub" in src
    assert "_inject_execute_payload_into_skill_args" in src
