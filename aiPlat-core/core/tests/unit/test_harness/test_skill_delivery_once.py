"""skill_delivery=once: after a successful primary skill, do not re-invoke it."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


@pytest.mark.asyncio
async def test_act_blocks_repeat_skill_when_delivery_once():
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    loop._init_routing_id = lambda state: "rid"  # type: ignore[method-assign]
    loop._dispatch_skill_call = AsyncMock(return_value="SHOULD_NOT_RUN")  # type: ignore[method-assign]
    loop._dispatch_tool_call = AsyncMock(return_value="tool")  # type: ignore[method-assign]
    loop._emit_no_action = AsyncMock()  # type: ignore[method-assign]

    state = LoopState(
        current=LoopStateEnum.ACTING,
        context={
            "reasoning": '{"type":"skill_call","skill":"architecture_design","input":"prd"}',
            "_skill_delivery": "once",
            "_primary_skill_delivered": "architecture_design",
            "_primary_skill_output": "ARCH_DOC_BODY_" + ("x" * 80),
        },
    )
    out = await loop._act(state)
    assert "already delivered" in out
    assert "ARCH_DOC_BODY_" in out
    loop._dispatch_skill_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_act_allows_first_skill_when_not_yet_delivered():
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    loop._init_routing_id = lambda state: "rid"  # type: ignore[method-assign]
    loop._dispatch_skill_call = AsyncMock(return_value="skill-ok")  # type: ignore[method-assign]
    loop._emit_no_action = AsyncMock()  # type: ignore[method-assign]

    state = LoopState(
        current=LoopStateEnum.ACTING,
        context={
            "reasoning": '{"type":"skill_call","skill":"architecture_design","input":"prd"}',
            "_skill_delivery": "once",
        },
    )
    out = await loop._act(state)
    assert out == "skill-ok"
    loop._dispatch_skill_call.assert_awaited_once()


def test_skill_delivery_body_strips_delivery_footer():
    state = LoopState(
        current=LoopStateEnum.OBSERVING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_output": (
                "# Architecture\n\n" + ("section " * 20) + "\n\n"
                "[DELIVERY] Skill `architecture_design` succeeded. Next response MUST be DONE"
            ),
        },
    )
    body = ReActLoop._skill_delivery_body(state)
    assert body.startswith("# Architecture")
    assert "[DELIVERY]" not in body
    assert len(body) >= 40


def test_empty_done_falls_back_to_skill_body():
    """Short/empty DONE answer must not wipe a delivered skill artifact."""
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_delivered": "architecture_design",
            "_primary_skill_output": "## 上下文与假设\n\n" + ("钉钉 API 未开放\n" * 10),
        },
    )
    body = ReActLoop._skill_delivery_body(state)
    assert "钉钉 API 未开放" in body
    # Simulate coerce used on DONE path
    final_text = ""
    if (not final_text or len(final_text) < 40) and body:
        final_text = body
    assert final_text == body
