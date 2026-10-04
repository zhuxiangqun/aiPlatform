"""POST /executions/{id}/cancel marks running agent rows cancelled."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.api.routers import executions_trace


@pytest.mark.asyncio
async def test_cancel_running_agent_execution():
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-cancel-1",
            "agent_id": "architect_agent",
            "status": "running",
            "start_time": time.time() - 30,
            "input": {"message": "x"},
            "output": None,
            "metadata": {"stream": True},
        }
    )
    store.get_skill_execution = AsyncMock(return_value=None)
    store.upsert_agent_execution = AsyncMock()
    store.close_running_syscall_events = AsyncMock(return_value=1)
    store.set_run_graph_status = AsyncMock()
    store.append_run_event = AsyncMock()

    rt = MagicMock()
    rt.execution_store = store

    app = FastAPI()
    app.include_router(executions_trace.router, prefix="/api/core")
    app.dependency_overrides[executions_trace.get_kernel_runtime] = lambda: rt

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/core/executions/run-cancel-1/cancel",
            json={"reason": "user_stop"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["already_terminal"] is False
    store.upsert_agent_execution.assert_awaited()
    patch = store.upsert_agent_execution.await_args.args[0]
    assert patch["status"] == "cancelled"
    assert "user_stop" in str(patch.get("error") or "")


@pytest.mark.asyncio
async def test_cancel_returns_when_upsert_hangs():
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-hang-cancel",
            "agent_id": "qa_agent",
            "status": "running",
            "start_time": time.time() - 200,
            "input": {},
            "output": None,
            "metadata": {},
        }
    )
    store.get_skill_execution = AsyncMock(return_value=None)

    async def _never(_patch):
        import asyncio
        await asyncio.sleep(30)

    store.upsert_agent_execution = _never
    store.close_running_syscall_events = AsyncMock(return_value=0)
    store.set_run_graph_status = AsyncMock()
    store.append_run_event = AsyncMock()

    rt = MagicMock()
    rt.execution_store = store
    app = FastAPI()
    app.include_router(executions_trace.router, prefix="/api/core")
    app.dependency_overrides[executions_trace.get_kernel_runtime] = lambda: rt
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/core/executions/run-hang-cancel/cancel",
            json={"reason": "user_stop"},
            timeout=8.0,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_already_terminal_is_idempotent():
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-done",
            "agent_id": "architect_agent",
            "status": "timeout",
            "start_time": time.time() - 100,
            "error": "already",
            "metadata": {},
        }
    )
    store.upsert_agent_execution = AsyncMock()
    rt = MagicMock()
    rt.execution_store = store
    app = FastAPI()
    app.include_router(executions_trace.router, prefix="/api/core")
    app.dependency_overrides[executions_trace.get_kernel_runtime] = lambda: rt
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/core/executions/run-done/cancel", json={})
    assert resp.status_code == 200
    assert resp.json()["already_terminal"] is True
    store.upsert_agent_execution.assert_not_awaited()
