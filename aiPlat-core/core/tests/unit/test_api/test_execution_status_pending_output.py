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
