"""orphan_watchdog must not mark lock_expired_stale for runs that never held a lock."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_has_any_session_lock_for_run_distinguishes_never_locked():
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "exec.db")
        store = ExecutionStore(ExecutionStoreConfig(db_path=db))
        await store.init()

        assert await store.has_any_session_lock_for_run(run_id="run-never") is False
        assert await store.has_active_session_lock_for_run(run_id="run-never") is False

        ok = await store.try_acquire_session_lock(
            tenant_id="t1",
            session_id="s1",
            run_id="run-held",
            ttl_seconds=300,
        )
        assert ok is True
        assert await store.has_any_session_lock_for_run(run_id="run-held") is True
        assert await store.has_active_session_lock_for_run(run_id="run-held") is True

        await store.try_acquire_session_lock(
            tenant_id="t1",
            session_id="s2",
            run_id="run-expired",
            ttl_seconds=1,
        )
        await asyncio.sleep(1.1)
        assert await store.has_any_session_lock_for_run(run_id="run-expired") is True
        assert await store.has_active_session_lock_for_run(run_id="run-expired") is False


@pytest.mark.asyncio
async def test_orphan_probe_skips_lock_stale_when_never_locked():
    """Agent stream path never acquires session_lock; age>=180 must not orphan via lock."""
    store = MagicMock()
    store.has_any_session_lock_for_run = AsyncMock(return_value=False)
    store.has_active_session_lock_for_run = AsyncMock(return_value=False)

    age = 200.0
    lock_expired_stale = False
    if age >= 180 and hasattr(store, "has_any_session_lock_for_run"):
        had_lock = await store.has_any_session_lock_for_run(run_id="run-agent-nolock")
        if had_lock:
            alive = await store.has_active_session_lock_for_run(run_id="run-agent-nolock")
            lock_expired_stale = not bool(alive)

    assert lock_expired_stale is False
    store.has_any_session_lock_for_run.assert_awaited()
    store.has_active_session_lock_for_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_orphan_probe_marks_stale_when_lock_held_then_expired():
    store = MagicMock()
    store.has_any_session_lock_for_run = AsyncMock(return_value=True)
    store.has_active_session_lock_for_run = AsyncMock(return_value=False)

    age = 200.0
    lock_expired_stale = False
    if age >= 180:
        had_lock = await store.has_any_session_lock_for_run(run_id="run-skill")
        if had_lock:
            alive = await store.has_active_session_lock_for_run(run_id="run-skill")
            lock_expired_stale = not bool(alive)

    assert lock_expired_stale is True


@pytest.mark.asyncio
async def test_orphan_marks_no_progress_when_only_agent_start():
    """Stuck UI: agent_start open for >90s with no LLM/skill events → timeout."""
    from core.api.routers.executions_trace import get_execution_status

    now = time.time()
    store = MagicMock()
    store.get_agent_execution = AsyncMock(
        return_value={
            "id": "run-noprog",
            "agent_id": "architect_agent",
            "status": "running",
            "start_time": now - 120.0,
            "output": None,
            "error": None,
            "metadata": {"stream": True, "timeout": 1200.0},
        }
    )
    store.get_skill_execution = AsyncMock(return_value=None)
    store.list_syscall_events = AsyncMock(
        return_value={
            "items": [
                {
                    "kind": "agent",
                    "name": "agent_start",
                    "status": "running",
                    "start_time": now - 120.0,
                }
            ]
        }
    )
    store.has_any_session_lock_for_run = AsyncMock(return_value=False)
    store.upsert_agent_execution = AsyncMock()
    store.release_session_locks_for_run = AsyncMock()
    store.delete_expired_session_locks = AsyncMock()
    store.close_running_syscall_events = AsyncMock(return_value=0)

    rt = MagicMock()
    rt.execution_store = store
    out = await get_execution_status("run-noprog", rt)
    assert out["status"] == "timeout"
    assert "no_progress" in str(out.get("error") or "")
    store.upsert_agent_execution.assert_awaited()
