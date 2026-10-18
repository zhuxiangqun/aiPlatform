"""auto_done must eager-finalize Agent row (same hang class as skill_delivery_once).

Regression: canvas shows 「完成 · 自动收尾」while top badge stays 「执行中 running」
because POST_LOOP/SECI hangs after LoopState FINISHED without upserting the Agent row.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.harness.execution.loop._facade import PlanExecuteLoop, ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


CORE = Path(__file__).resolve().parents[3]  # aiPlat-core/core


def test_auto_done_path_wires_eager_finalize():
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert 'source="reason_auto_done"' in src
    assert "def _commit_react_finish" in src
    assert "react finalize exception; fail-closed" in src
    assert "str(_out)[:50000]" in src
    assert "async def _eager_finalize_agent_row" in src
    assert 'source="reason_parsed_none"' in src
    assert 'source="reason_not_found_streak"' in src
    assert 'source="reason_final_answer"' in src
    assert 'source="observe_skill_delivery_once"' in src
    assert 'source="observe_done_marker"' in src
    # Ungated FINISHED seals must run acceptance/done_verify first.
    assert src.count("_acceptance_gate(state)") >= 5
    assert "_none_veto = self._acceptance_gate(state)" in src
    assert "_nf_veto = self._acceptance_gate(state)" in src
    assert "_obs_veto = self._acceptance_gate(state)" in src
    assert "emit_pre_llm_prep_close" in src
    assert "eager_finalize:{source}" in src
    assert "async def _close_leftover_running_syscalls" in src
    assert 'source="reason_auto_done"' in src
    assert "def _commit_react_finish" in src
    assert "react finalize exception; fail-closed" in src


def test_plan_execute_finish_checks_done_verify():
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert "def _plan_done_verify_reason" in src
    assert "def _block_plan_finish" in src
    assert "def _plan_seal_block_reason" in src
    assert "def _bind_plan_completion" in src
    assert "def _seal_plan_finish" in src
    assert src.count("_seal_plan_finish(state)") >= 2
    assert src.count("_finalize_plan_or_block(") >= 2
    assert "plan finalize exception; fail-closed" in src
    assert "coding_veto_exhausted" in src
    assert "seal_before_finish" in src
    assert "execution_seal" in src
    assert "coding_deliverable_veto" in src
    # Must not spin a throwaway ReActLoop just to seal.
    plan_fn = src.split("def _seal_plan_finish", 1)[1].split("def _block_plan_finish", 1)[0]
    assert "ReActLoop(" not in plan_fn
    assert "plan_execute_finish" in src
    assert "plan_execute_empty_plan" in src
    assert "_record_plan_step_receipt" in src
    seal = (CORE / "harness/execution/execution_seal.py").read_text(encoding="utf-8")
    assert "fail-closed for coding/review" in seal


def test_plan_finish_binds_receipt_and_blocks_missing_review():
    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "已经修好了",
            "_user_task": "实现一个 Python 函数并落盘",
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_done_verify": {
                "require_review": True,
                "min_output_length": 10,
                "reject_trivial_done": False,
            },
            "_primary_skill_delivered": True,
            "_followup_skills_done": [],
            "_tool_receipts": [],
        },
        step_count=1,
    )
    reason = loop._seal_plan_finish(state)
    assert reason
    assert str(state.context["output"]).startswith("[未核验]")
    assert state.context.get("_completion_seal") == "unverified"
    blocked = loop._block_plan_finish(state, reason)
    assert blocked.current == LoopStateEnum.ERROR
    assert state.context.get("_require_review_incomplete") is True


@pytest.mark.asyncio
async def test_plan_finalize_exception_fail_closed_for_coding():
    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "## FILE: a.py\n" + ("x" * 40),
            "_done_verify": {"require_review": True},
            "_bound_skill_ids": ["code_generation"],
            "_run_id": "run-plan-fin",
        },
        step_count=1,
    )

    async def _boom(**_kwargs):
        raise RuntimeError("store down")

    with patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery",
        new=_boom,
    ):
        blocked = await loop._finalize_plan_or_block(state, source="plan_execute_finish")
    assert blocked is not None
    assert blocked.current == LoopStateEnum.ERROR
    assert "plan finalize exception" in str(state.context.get("error") or "")


@pytest.mark.asyncio
async def test_plan_finalize_exception_soft_for_chat():
    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "hello there this is a plain greeting for you",
            "_bound_skill_ids": ["chitchat"],
            "_done_verify": {"min_output_length": 0},
        },
        step_count=1,
    )

    async def _boom(**_kwargs):
        raise RuntimeError("store down")

    with patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery",
        new=_boom,
    ):
        blocked = await loop._finalize_plan_or_block(state, source="plan_execute_empty_plan")
    assert blocked is None
    assert state.current == LoopStateEnum.REASONING


def test_commit_react_finish_honors_force_failed_status():
    loop = ReActLoop(config=LoopConfig(max_steps=2), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={"_force_failed_status": "timeout", "output": "partial"},
        step_count=1,
    )
    out = loop._commit_react_finish(state)
    assert out.current == LoopStateEnum.ERROR
    assert "forced_timeout" in str(state.context.get("error") or "")


@pytest.mark.asyncio
async def test_react_finalize_exception_fail_closed_for_coding():
    loop = ReActLoop(config=LoopConfig(max_steps=2), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_run_id": "run-react-fin",
            "_agent_id": "coder",
            "_bound_skill_ids": ["code_generation"],
            "_done_verify": {"require_review": True},
        },
        step_count=1,
    )

    async def _boom(**_kwargs):
        raise RuntimeError("store down")

    with patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery",
        new=_boom,
    ):
        ok = await loop._eager_finalize_agent_row(
            state,
            output_text="## FILE: a.py\n" + ("x" * 40),
            source="observe_skill_delivery_once",
        )
    assert ok is False
    out = loop._commit_react_finish(state)
    assert out.current == LoopStateEnum.ERROR
    assert "react finalize exception" in str(state.context.get("error") or "")


def test_plan_finish_plain_answer_stays():
    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "output": "hello there this is a plain greeting for you",
            "_user_task": "打个招呼",
            "_bound_skill_ids": ["chitchat"],
            "_done_verify": {"min_output_length": 10, "reject_trivial_done": False},
            "_tool_receipts": [],
        },
        step_count=1,
    )
    assert loop._seal_plan_finish(state) is None
    assert state.context["output"] == "hello there this is a plain greeting for you"
    assert state.context.get("_completion_seal") == "ok"


def test_plan_step_records_tool_receipt():
    loop = PlanExecuteLoop(config=LoopConfig(max_steps=4), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={"_tool_receipts": []},
        step_count=1,
    )
    loop._record_plan_step_receipt(
        state, tool="code_generation", result="## FILE: a.py\nprint(1)\n"
    )
    rows = state.context.get("_tool_receipts") or []
    assert rows and rows[-1]["status"] == "ok"
    assert rows[-1]["tool"] == "code_generation"
    assert state.context.get("_primary_skill_delivered") is True


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
