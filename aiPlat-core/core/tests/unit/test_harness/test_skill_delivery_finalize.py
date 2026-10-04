"""skill_delivery=once must finalize Agent row even if POST_LOOP hangs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.harness.utils.execute_session import (
    extract_skill_delivery_answer,
    finalize_agent_after_skill_delivery,
    orphan_skill_delivery_answer,
)


def test_orphan_skill_delivery_waits_for_delivery_once_not_bare_skill():
    """Status orphan must not seal after code_generation alone (skip autoreview)."""
    code_body = "function getTasks(){ return apiClient.get('/api/tasks'); }\n" * 3
    mid_loop = [
        {
            "kind": "skill",
            "name": "code_generation",
            "status": "success",
            "result": {"output": code_body},
            "end_time": 100.0,
        },
        {
            "kind": "done",
            "name": "auto_done",
            "status": "ok",
            "result": {"answer": "please wait"},
            "end_time": 50.0,
        },
    ]
    assert orphan_skill_delivery_answer(mid_loop) == ""

    sealed = mid_loop + [
        {
            "kind": "done",
            "name": "skill_delivery_once",
            "status": "ok",
            "result": {"answer": code_body[:80], "source": "primary_skill"},
            "end_time": 200.0,
        },
    ]
    out = orphan_skill_delivery_answer(sealed)
    assert code_body[:40] in out
    assert len(out) >= 40


def test_orphan_auto_done_seals_conversational_not_coding():
    """qa_agent-style: skill + auto_done must recover; coding auto_done must wait."""
    cases = "SMK-001 上报主路径\n" + ("步骤：打开页面并提交表单。\n" * 6)
    qa_items = [
        {
            "kind": "skill",
            "name": "test_case_generation",
            "status": "success",
            "result": {"output": cases},
        },
        {
            "kind": "skill",
            "name": "test_case_generation",
            "status": "running",
            "result": {},
        },
        {
            "kind": "done",
            "name": "auto_done",
            "status": "ok",
            "result": {"answer": cases, "source": "auto_done"},
        },
    ]
    out = orphan_skill_delivery_answer(qa_items)
    assert "SMK-001" in out
    assert len(out) >= 40

    in_flight = [
        {
            "kind": "skill",
            "name": "test_case_generation",
            "status": "running",
        },
        {
            "kind": "done",
            "name": "auto_done",
            "status": "ok",
            "result": {"answer": cases, "source": "auto_done"},
        },
    ]
    assert orphan_skill_delivery_answer(in_flight) == ""


def test_extract_skill_delivery_answer_from_done_and_skill():
    assert "现场" in extract_skill_delivery_answer(
        {"result": {"answer": "现场巡检报障小应用" + ("x" * 40)}}
    )
    body = extract_skill_delivery_answer(
        {"result": {"output": {"title": "现场巡检报障小应用", "context": "车间"}}}
    )
    assert "现场巡检报障小应用" in body


def test_extract_skill_delivery_answer_skips_skill_call_envelope():
    env = (
        '{"type":"skill_call","skill":"code_generation","input":{"code":"'
        + ("x" * 50)
        + '"}}'
    )
    assert extract_skill_delivery_answer({"result": {"answer": env, "source": "auto_done"}}) == ""
    assert "现场" in extract_skill_delivery_answer(
        {"result": {"answer": "现场巡检报障小应用" + ("x" * 40)}}
    )


@pytest.mark.asyncio
async def test_finalize_skips_pending_skill_call_envelope():
    """Do not seal {"type":"skill_call",...} as completed deliverable."""
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-env",
            "agent_id": "frontend_engineer",
            "status": "running",
            "input": {"message": "生成前端代码"},
            "start_time": 100.0,
        }
    )
    store.upsert_agent_execution = AsyncMock()
    body = (
        '{"type":"skill_call","skill":"code_generation","input":{'
        '"language":"typescript","code":"' + ("function x(){return 1;}\\n" * 8) + '"}}'
    )
    with patch("core.services.execution_store.get_execution_store", return_value=store):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-env",
            agent_id="frontend_engineer",
            output_text=body,
            start_time=100.0,
        )
    assert ok is False
    store.upsert_agent_execution.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_skips_non_deliverable_coding_clarify():
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-clarify",
            "agent_id": "frontend_engineer",
            "status": "running",
            "input": {
                "message": "根据 api_contracts 生成前端代码，使用 ## FILE: 格式",
            },
            "start_time": 100.0,
            "metadata": {},
        }
    )
    store.upsert_agent_execution = AsyncMock()
    store.list_syscall_events = AsyncMock(return_value={"items": []})
    store.append_run_event = AsyncMock()

    clarify = (
        '{"code": "I need more details on what specific Python code you want. '
        'Could you specify the function or class?", "language": "python"}'
    )
    with patch("core.services.execution_store.get_execution_store", return_value=store), patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-clarify",
            agent_id="frontend_engineer",
            output_text=clarify,
            start_time=100.0,
        )
    # Non-deliverable must seal as failed (not leave status=running forever).
    assert ok is True
    store.upsert_agent_execution.assert_awaited()
    sealed = store.upsert_agent_execution.await_args.args[0]
    assert sealed["status"] == "failed"
    assert "non-deliverable" in str(sealed.get("error") or "").lower() or sealed.get("error")

    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-x",
            "agent_id": "architect_agent",
            "status": "running",
            "input": {"message": "prd"},
            "metadata": {"stream": True, "timeout": 1200},
            "start_time": 100.0,
            "trace_id": "t1",
        }
    )
    store.upsert_agent_execution = AsyncMock()
    store.append_run_event = AsyncMock()

    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.observation.run_graph.close_node", new_callable=AsyncMock
    ) as close_n, patch(
        "core.harness.observation.run_graph.open_node", new_callable=AsyncMock
    ) as open_n, patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ) as mark_done, patch(
        "core.management.execution_quality_review.review_execution_output",
        return_value={"ok": True, "verdict": "pass"},
    ), patch(
        "core.management.execution_quality_review.ensure_architecture_section_fields",
        side_effect=lambda x: x,
    ), patch(
        "core.management.execution_quality_review._unwrap_output",
        side_effect=lambda x: x.get("text") if isinstance(x, dict) else x,
    ):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-x",
            agent_id="architect_agent",
            output_text='{"title":"现场巡检报障小应用","context":"车间","overview":"'
            + ("架构 " * 20)
            + '"}',
            start_time=100.0,
            trace_id="t1",
        )
    assert ok is True
    store.upsert_agent_execution.assert_awaited()
    args = store.upsert_agent_execution.await_args.args[0]
    assert args["status"] == "completed"
    assert "现场巡检报障小应用" in str(args["output"])
    assert args["metadata"].get("skill_delivery_finalize") is True
    close_n.assert_awaited()
    open_n.assert_awaited()
    mark_done.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_idempotent_when_already_completed():
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-y",
            "status": "completed",
            "output": {"text": "already good product " + ("y" * 40)},
            "metadata": {},
        }
    )
    store.upsert_agent_execution = AsyncMock()
    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ) as mark_done:
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-y",
            agent_id="architect_agent",
            output_text="new body " + ("z" * 40),
        )
        assert ok is True
        store.upsert_agent_execution.assert_not_awaited()
        mark_done.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_marks_failed_when_qr_thin_code_stub():
    """Hard coding QR fail must not leave status=completed (false green)."""
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-thin",
            "agent_id": "frontend_engineer",
            "status": "running",
            "input": {"message": "根据 api_contracts 生成前端代码 ## FILE"},
            "start_time": 100.0,
            "trace_id": "t-thin",
        }
    )
    store.upsert_agent_execution = AsyncMock()
    store.append_run_event = AsyncMock()

    # Long enough to pass early length gate; QR reports thin_code_stub
    body = "## FILE: src/App.tsx\n" + ("// placeholder comment\n" * 30)
    qr_fail = {
        "ok": False,
        "verdict": "fail",
        "headline": "流程已完成，产物未达可验收质量",
        "issues": [
            {
                "severity": "error",
                "code": "thin_code_stub",
                "message": "空壳",
            }
        ],
    }

    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.observation.run_graph.close_node", new_callable=AsyncMock
    ), patch(
        "core.harness.observation.run_graph.open_node", new_callable=AsyncMock
    ), patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ) as mark_done, patch(
        "core.management.execution_quality_review.is_non_deliverable_coding_output",
        return_value=False,
    ), patch(
        "core.management.execution_quality_review.review_execution_output",
        return_value=qr_fail,
    ), patch(
        "core.management.execution_quality_review.ensure_architecture_section_fields",
        side_effect=lambda x: x,
    ), patch(
        "core.management.execution_quality_review.sanitize_architecture_third_party",
        side_effect=lambda x, *_a, **_k: x,
    ), patch(
        "core.management.execution_quality_review._unwrap_output",
        side_effect=lambda x: x.get("text") if isinstance(x, dict) else x,
    ):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-thin",
            agent_id="frontend_engineer",
            output_text=body,
            start_time=100.0,
            trace_id="t-thin",
        )
    assert ok is True
    args = store.upsert_agent_execution.await_args.args[0]
    assert args["status"] == "failed"
    assert args["metadata"].get("quality_block_completed") is True
    assert args["metadata"].get("quality_review", {}).get("verdict") == "fail"
    mark_done.assert_awaited()
    assert mark_done.await_args.kwargs.get("status") == "failed" or (
        len(mark_done.await_args.args) > 1 and mark_done.await_args.args[1] == "failed"
    )


@pytest.mark.asyncio
async def test_finalize_orphan_watch_skips_quality_review():
    """Status poll budget is 8s — QR on watchdog must not block the seal."""
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-qa-orphan",
            "agent_id": "qa_agent",
            "status": "running",
            "input": {"message": "请设计冒烟用例"},
            "start_time": 100.0,
        }
    )
    store.upsert_agent_execution = AsyncMock()
    store.append_run_event = AsyncMock()
    store.list_syscall_events = AsyncMock(return_value={"items": []})
    body = "SMK-001 上报主路径\n" + ("打开页面并提交。\n" * 8)
    qr = MagicMock(side_effect=AssertionError("QR must not run on orphan watch"))
    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.observation.run_graph.close_node", new_callable=AsyncMock
    ), patch(
        "core.harness.observation.run_graph.open_node", new_callable=AsyncMock
    ), patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ), patch(
        "core.management.execution_quality_review.review_execution_output", qr
    ):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-qa-orphan",
            agent_id="qa_agent",
            output_text=body,
            start_time=100.0,
            metadata_extra={
                "orphan_watchdog": True,
                "finalize_source": "status_orphan_watch",
            },
        )
    assert ok is True
    qr.assert_not_called()
    args = store.upsert_agent_execution.await_args.args[0]
    assert args["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_upserts_before_hung_graph_close():
    """Agent row must leave running even if RunGraph close never returns."""
    import asyncio as aio

    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-124d89d5ef3f",
            "agent_id": "qa_agent",
            "status": "running",
            "input": {"message": "请设计冒烟用例"},
            "start_time": 100.0,
        }
    )
    store.upsert_agent_execution = AsyncMock()
    store.append_run_event = AsyncMock()
    store.list_syscall_events = AsyncMock(return_value={"items": []})
    store.close_running_syscall_events = AsyncMock(return_value=1)

    async def _hang(*_a, **_k):
        await aio.sleep(30)

    real_wf = aio.wait_for

    async def _wf(coro, timeout=None):
        if timeout == 4.0:
            return await real_wf(coro, timeout=0.05)
        return await real_wf(coro, timeout=timeout)

    body = "SMK-001 上报主路径\n" + ("打开页面并提交。\n" * 8)
    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.observation.run_graph.close_node", _hang
    ), patch(
        "core.harness.observation.run_graph.open_node", new_callable=AsyncMock
    ), patch(
        "core.harness.observation.run_graph.mark_run_done", new_callable=AsyncMock
    ), patch(
        "asyncio.wait_for", _wf
    ), patch(
        "core.management.execution_quality_review.review_execution_output",
        return_value={"ok": True, "verdict": "pass", "issues": []},
    ), patch(
        "core.management.execution_quality_review.quality_review_blocks_success",
        return_value=False,
    ), patch(
        "core.management.execution_quality_review.ensure_architecture_section_fields",
        side_effect=lambda x: x,
    ), patch(
        "core.management.execution_quality_review.sanitize_architecture_third_party",
        side_effect=lambda x, *_a, **_k: x,
    ), patch(
        "core.management.execution_quality_review._unwrap_output",
        side_effect=lambda x: x.get("text") if isinstance(x, dict) else x,
    ):
        ok = await finalize_agent_after_skill_delivery(
            run_id="run-124d89d5ef3f",
            agent_id="qa_agent",
            output_text=body,
            start_time=100.0,
            metadata_extra={"finalize_source": "reason_auto_done"},
        )
    assert ok is True
    first = store.upsert_agent_execution.await_args_list[0].args[0]
    assert first["status"] == "completed"
    assert first["id"] == "run-124d89d5ef3f"
