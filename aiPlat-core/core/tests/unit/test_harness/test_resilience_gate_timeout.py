"""ResilienceGate must fail-fast on timeout even when fn uses to_thread."""

from __future__ import annotations

import asyncio
import time

import pytest

from core.harness.infrastructure.gates.resilience_gate import ResilienceGate


@pytest.mark.asyncio
async def test_timeout_abandons_uncancelable_thread_work():
    """Bare wait_for would block until the thread ends; we must raise at deadline."""
    gate = ResilienceGate()
    started = time.monotonic()

    async def _slow_uncancelable():
        # Simulate OpenAI sync client in to_thread — cancel does not stop the sleep.
        await asyncio.to_thread(time.sleep, 2.5)

    with pytest.raises(asyncio.TimeoutError):
        await gate.run(_slow_uncancelable, retries=0, timeout_seconds=0.3)

    elapsed = time.monotonic() - started
    assert elapsed < 1.2, f"fail-fast timeout took {elapsed:.2f}s (should abandon ~0.3s)"


@pytest.mark.asyncio
async def test_success_within_timeout():
    gate = ResilienceGate()

    async def _ok():
        await asyncio.sleep(0.05)
        return "ok"

    assert await gate.run(_ok, retries=0, timeout_seconds=1.0) == "ok"


@pytest.mark.asyncio
async def test_timeout_error_never_retried_even_when_oserror_listed():
    """Root cause of multi-minute hangs: TimeoutError ⊂ OSError + retries=2.

    Without hard-exclude, one 180s timeout becomes ~540s with zombie HTTP.
    """
    gate = ResilienceGate()
    calls = {"n": 0}

    async def _always_timeout():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        raise asyncio.TimeoutError("operation timed out after 180s")

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await gate.run(
            _always_timeout,
            retries=2,
            timeout_seconds=None,
            retry_on=(ConnectionError, OSError, RuntimeError),
        )
    elapsed = time.monotonic() - started

    assert calls["n"] == 1, f"TimeoutError must not retry; got {calls['n']} attempts"
    assert elapsed < 0.5, f"fail-fast took {elapsed:.2f}s (must not 3× backoff)"
    # Sanity: the inheritance trap that caused production hangs still holds.
    assert isinstance(asyncio.TimeoutError(), OSError)


@pytest.mark.asyncio
async def test_classified_timeout_never_retried():
    from core.harness.infrastructure.gates.error_translator import (
        ClassifiedError,
        FailoverReason,
    )

    gate = ResilienceGate()
    calls = {"n": 0}

    async def _classified_timeout():
        calls["n"] += 1
        raise ClassifiedError(
            reason=FailoverReason.timeout,
            message="read timed out",
            retryable=True,
        )

    with pytest.raises(ClassifiedError):
        await gate.run(
            _classified_timeout,
            retries=2,
            timeout_seconds=None,
            retry_on=(ConnectionError, OSError, RuntimeError),
        )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_connection_error_still_retried():
    gate = ResilienceGate()
    calls = {"n": 0}

    async def _conn_fail():
        calls["n"] += 1
        raise ConnectionError("reset by peer")

    with pytest.raises(ConnectionError):
        await gate.run(
            _conn_fail,
            retries=2,
            timeout_seconds=None,
            retry_on=(ConnectionError, OSError, RuntimeError),
            backoff_base_seconds=0.01,
            backoff_max_seconds=0.02,
        )
    assert calls["n"] == 3
