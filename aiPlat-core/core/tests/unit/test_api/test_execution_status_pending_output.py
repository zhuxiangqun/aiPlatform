"""Status poll must not report completed+empty while agent row is still upserting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _rt(store):
    rt = MagicMock()
    rt.execution_store = store
    return rt


@pytest.mark.asyncio
async def test_run_graph_completed_without_row_returns_pending_output():
    from core.api.routers.executions_trace import get_execution_status

    store = MagicMock()
    store.get_agent_execution = AsyncMock(return_value=None)
    store.get_skill_execution = AsyncMock(return_value=None)
    store.get_run_graph_status = AsyncMock(return_value="completed")
    store.has_run_end = AsyncMock(return_value=False)

    out = await get_execution_status("run-race-1", _rt(store))
    assert out["status"] == "running"
    assert out.get("pending_output") is True
    assert out.get("output") is None


@pytest.mark.asyncio
async def test_run_graph_completed_empty_row_is_terminal_not_pending():
    """Terminal empty row must not spin forever as pending_output."""
    from core.api.routers.executions_trace import get_execution_status

    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        side_effect=[
            None,
            {"status": "completed", "output": None, "error": None, "duration_ms": 100},
        ]
    )
    store.get_skill_execution = AsyncMock(return_value=None)
    store.get_run_graph_status = AsyncMock(return_value="completed")

    out = await get_execution_status("run-empty-done", _rt(store))
    assert out["status"] == "completed"
    assert out.get("pending_output") is not True


def test_blank_run_end_is_not_treated_as_completed():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[3] / "api/routers/executions_trace.py"
    ).read_text(encoding="utf-8")
    assert 'elif st in ("completed", "ok", "success", "done"):' in src
    assert 'elif st in ("completed", "ok", "success", "done", ""):' not in src
    assert "Blank run_end status is not a success seal." in src
    assert "def _apply_sealed_failure_status" in src
    eng = (
        Path(__file__).resolve().parents[3] / "harness/execution/pipeline_engine.py"
    ).read_text(encoding="utf-8")
    assert "_trace_force" in eng
    assert '_trace_status = "timeout" if _trace_force == "timeout" else "failed"' in eng


def test_apply_sealed_failure_status_overrides_completed():
    from core.harness.utils.execute_session import _sealed_failure_status

    assert (
        _sealed_failure_status(
            {
                "force_failed_status": "timeout",
                "done_verify_reason": "llm_timeout",
            }
        )
        == "timeout"
    )
    assert _sealed_failure_status({}) == ""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[3] / "api/routers/executions_trace.py"
    ).read_text(encoding="utf-8")
    # Agent row + run_graph + run_events all apply the seal.
    assert src.count("_apply_sealed_failure_status(") >= 3
    assert "run_graph status row re-read failed" in src


@pytest.mark.asyncio
async def test_run_graph_completed_with_row_returns_output():
    from core.api.routers.executions_trace import get_execution_status

    store = MagicMock()
    # First lookup empty (agent), second path re-read after graph finds the row
    store.get_agent_execution = AsyncMock(
        side_effect=[
            None,
            {
                "status": "completed",
                "output": {"text": "architecture draft with enough body for review"},
                "error": None,
                "duration_ms": 1200,
            },
        ]
    )
    store.get_skill_execution = AsyncMock(return_value=None)
    store.get_run_graph_status = AsyncMock(return_value="completed")

    out = await get_execution_status("run-race-2", _rt(store))
    assert out["status"] == "completed"
    assert out.get("pending_output") is not True
    assert out.get("output") is not None
