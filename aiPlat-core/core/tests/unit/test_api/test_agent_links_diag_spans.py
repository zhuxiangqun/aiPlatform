"""Diagnostic span merge for workspace agent Links (syscall + run_graph)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_merged_diag_spans_includes_run_graph_nodes():
    from core.harness.utils.diag_spans import merged_diag_spans

    store = MagicMock()
    store.list_syscall_events = AsyncMock(
        return_value={
            "items": [
                {
                    "id": "sys-1",
                    "kind": "llm",
                    "name": "generate",
                    "status": "timeout",
                    "start_time": 100.0,
                    "duration_ms": 180000,
                }
            ]
        }
    )
    store.list_run_graph_nodes = AsyncMock(
        return_value=[
            {
                "node_id": "agent:architect:start",
                "kind": "agent",
                "name": "agent_start",
                "status": "error",
                "start_time": 90.0,
                "duration_ms": 180000,
            },
            {
                "node_id": "step:1",
                "parent_id": "agent:architect:start",
                "kind": "step",
                "name": "react_step",
                "status": "running",
                "start_time": 95.0,
            },
        ]
    )

    spans = await merged_diag_spans(store, "run-abc", "trace-xyz")
    names = [str(s.get("name")) for s in spans]
    assert any("agent_start" in n or "agent:" in n for n in names)
    assert any("react_step" in n or "step:" in n for n in names)
    assert any("generate" in n or "llm" in n for n in names)
    assert len(spans) >= 3


@pytest.mark.asyncio
async def test_syscall_spans_drop_empty_kind_name_ghosts():
    from core.harness.utils.diag_spans import syscall_spans

    store = MagicMock()
    store.list_syscall_events = AsyncMock(
        return_value={
            "items": [
                {"id": "ghost", "kind": "", "name": "", "status": "completed"},
                {
                    "id": "ok",
                    "kind": "done",
                    "name": "skill_delivery_once",
                    "status": "ok",
                    "start_time": 1.0,
                },
            ]
        }
    )
    spans = await syscall_spans(store, "run-x", "trace-x")
    assert len(spans) == 1
    assert "skill_delivery" in str(spans[0].get("name") or "")
