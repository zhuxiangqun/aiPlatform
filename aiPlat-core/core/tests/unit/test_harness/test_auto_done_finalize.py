"""auto_done must eager-finalize Agent row (same hang class as skill_delivery_once).

Regression: canvas shows 「完成 · 自动收尾」while top badge stays 「执行中 running」
because POST_LOOP/SECI hangs after LoopState FINISHED without upserting the Agent row.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


CORE = Path(__file__).resolve().parents[3]  # aiPlat-core/core


def test_auto_done_path_wires_eager_finalize():
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert 'source="reason_auto_done"' in src
    assert "str(_out)[:50000]" in src
    assert "async def _eager_finalize_agent_row" in src
    assert 'source="reason_parsed_none"' in src
    assert 'source="reason_not_found_streak"' in src
    assert 'source="reason_final_answer"' in src
    assert 'source="observe_skill_delivery_once"' in src
    assert 'source="observe_done_marker"' in src
    assert "emit_pre_llm_prep_close" in src
    assert "eager_finalize:{source}" in src
    assert "async def _close_leftover_running_syscalls" in src
    assert "reason_auto_done_seal" in src


@pytest.mark.asyncio
async def test_step_auto_done_eager_finalizes_agent_row():
    """Plain-text reasoning (no tool call) → auto_done → finalize before POST_LOOP."""
    loop = ReActLoop(config=LoopConfig(max_steps=3), model=None, tools=[], skills=[])
    loop._acceptance_gate = lambda state: None  # type: ignore[method-assign]
    loop._trigger_hook = AsyncMock()  # type: ignore[method-assign]
    loop._apply_todo_done_markers = AsyncMock()  # type: ignore[method-assign]
    loop._detect_quality_drift = lambda reasoning, state: (False, "")  # type: ignore[method-assign]
    loop._skill_delivery_body = lambda state: ""  # type: ignore[method-assign]

    answer = "## 页面方案\n\n" + ("前端工程师交付说明。\n" * 8)

    async def _fake_reason(state: LoopState):
        return answer

    loop._reason = _fake_reason  # type: ignore[method-assign]

    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_run_id": "run-auto-done",
            "_agent_id": "frontend_engineer",
            "_trace_id": "tr-1",
            "_current_step_span_id": "step:1",
            "messages": [{"role": "user", "content": "做个列表页"}],
        },
        step_count=1,
    )

    store = MagicMock()
    store.add_syscall_event = AsyncMock()
    store.close_running_syscall_events = AsyncMock(return_value=1)
    fin = AsyncMock(return_value=True)

    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery", fin
    ):
        out = await loop.step(state)

    assert out.current == LoopStateEnum.FINISHED
    assert out.context.get("_agent_row_finalized") is True
    fin.assert_awaited_once()
    kwargs = fin.await_args.kwargs
    assert kwargs["run_id"] == "run-auto-done"
    assert kwargs["agent_id"] == "frontend_engineer"
    assert kwargs["metadata_extra"]["finalize_source"] == "reason_auto_done"
    assert "页面方案" in kwargs["output_text"]
    # syscall event must carry enough answer for orphan-watch fallback
    names = [c.args[0]["name"] for c in store.add_syscall_event.await_args_list if c.args]
    assert "auto_done" in names
    ev = next(c.args[0] for c in store.add_syscall_event.await_args_list if c.args[0].get("name") == "auto_done")
    assert len(str((ev.get("result") or {}).get("answer") or "")) >= 40
    store.close_running_syscall_events.assert_awaited()


@pytest.mark.asyncio
async def test_eager_finalize_survives_hung_pre_llm_prep_close():
    """SQLite lock on pre_llm_prep close must not skip Agent upsert."""
    loop = ReActLoop(config=LoopConfig(max_steps=2), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_run_id": "run-hang-prep",
            "_agent_id": "qa_agent",
            "_trace_id": "tr-h",
            "_current_step_span_id": "step:qa_agent:2",
        },
        step_count=2,
    )

    async def _hang(*_a, **_k):
        import asyncio

        await asyncio.sleep(30)

    fin = AsyncMock(return_value=True)
    with patch(
        "core.harness.utils.execute_session.emit_pre_llm_prep_close", _hang
    ), patch(
        "core.services.execution_store.get_execution_store", return_value=MagicMock()
    ), patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery", fin
    ):
        ok = await loop._eager_finalize_agent_row(
            state, output_text="SMK-001 上报主路径\n" + ("步骤。\n" * 8), source="reason_auto_done"
        )
    assert ok is True
    fin.assert_awaited_once()
