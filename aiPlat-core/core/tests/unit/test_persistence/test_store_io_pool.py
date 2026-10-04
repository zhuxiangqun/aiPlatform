"""Dedicated store IO pool must not share threads with LLM to_thread zombies."""
import asyncio
import threading

import pytest

from core.services.execution_store._base import run_store_io, _STORE_EXECUTOR


@pytest.mark.asyncio
async def test_run_store_io_uses_dedicated_executor():
    seen = {"name": None}

    def _sync():
        seen["name"] = threading.current_thread().name
        return 42

    out = await run_store_io(_sync)
    assert out == 42
    assert seen["name"] and seen["name"].startswith("aiplat_store")
    assert _STORE_EXECUTOR._max_workers >= 2


@pytest.mark.asyncio
async def test_run_store_io_unaffected_by_saturated_default_pool(monkeypatch):
    """Even if default to_thread is busy, store reads still complete."""
    import concurrent.futures

    # Occupy default executor with long sleepers
    default = concurrent.futures.thread._threads_queues  # noqa: touch
    loop = asyncio.get_running_loop()
    blockers = []
    for _ in range(4):
        blockers.append(loop.run_in_executor(None, lambda: __import__("time").sleep(0.3)))

    t0 = asyncio.get_running_loop().time()
    val = await asyncio.wait_for(run_store_io(lambda: "ok"), timeout=1.0)
    elapsed = asyncio.get_running_loop().time() - t0
    assert val == "ok"
    # Must not wait for the 0.3s blockers on the default pool
    assert elapsed < 0.25
    for b in blockers:
        b.cancel()
