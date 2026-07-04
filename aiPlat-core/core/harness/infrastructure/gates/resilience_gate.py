"""
ResilienceGate (Phase 3 - minimal).

Provides a simple retry wrapper for syscalls. In later phases it will support:
- configurable retry policies
- fallback chains across engines
- circuit breakers
"""

from __future__ import annotations
import logging

import asyncio
import random
import time
from typing import Any, Awaitable, Callable, Optional, Sequence, Type, TypeVar

T = TypeVar("T")


class ResilienceGate:
    def __init__(self) -> None:
        pass

    async def run(
        self,
        fn: Callable[[], Awaitable[T]],
        *,
        retries: int = 0,
        timeout_seconds: Optional[float] = None,
        retry_on: Sequence[Type[BaseException]] = (
            asyncio.TimeoutError,
            ConnectionError,
            OSError,
        ),
        backoff_base_seconds: float = 0.2,
        backoff_max_seconds: float = 2.0,
    ) -> T:
        last_exc: Optional[BaseException] = None
        for attempt in range(max(0, retries) + 1):
            try:
                if timeout_seconds is not None:
                    return await asyncio.wait_for(fn(), timeout=timeout_seconds)
                return await fn()
            except Exception as e:
                last_exc = e
                # ClassifiedError with retryable=True → always retry
                from core.harness.infrastructure.gates.error_translator import ClassifiedError
                if isinstance(e, ClassifiedError):
                    if not e.retryable:
                        raise
                    if attempt >= retries:
                        retry_msg = f"[RETRIED:{retries}] {e.reason.value} — {e.message[:200]}"
                        raise RuntimeError(retry_msg) from e
                elif not isinstance(e, tuple(retry_on)):
                    raise
                elif attempt >= retries:
                    retry_msg = f"[RETRIED:{retries}] {str(e)}"
                    try:
                        raise type(e)(retry_msg) from e
                    except TypeError:
                        raise RuntimeError(retry_msg) from e
                # ── Decorrelated jitter (hermes-aligned) ──
                # Golden-ratio hash prevents thundering-herd when multiple
                # concurrent workers retry the same provider simultaneously.
                # `time_ns ^ (tick * golden_ratio)` decorrelates seeds even
                # on coarse-resolution clocks.
                try:
                    import os as _os
                    _jitter_ratio = float(_os.getenv("AIPLAT_JITTER_RATIO", "0.5") or "0.5")
                    _base = backoff_base_seconds * (2 ** attempt)
                    delay = min(backoff_max_seconds, _base)

                    # Overflow guard: if exponent is too large, cap at max_delay
                    if attempt >= 63 or backoff_base_seconds <= 0:
                        delay = backoff_max_seconds

                    # Decorrelated jitter via golden-ratio hash of time_ns
                    _tick = time.time_ns() if hasattr(time, "time_ns") else int(time.time() * 1e9)
                    _seed = (_tick ^ (attempt * 0x9E3779B9)) & 0xFFFFFFFF
                    import random as _random_mod
                    _rng = _random_mod.Random(_seed)
                    delay = max(0.0, delay + _rng.uniform(0.0, _jitter_ratio * delay))
                    await asyncio.sleep(delay)
                except Exception:
                    # Fallback: simple backoff without jitter
                    await asyncio.sleep(min(backoff_max_seconds, backoff_base_seconds * (2 ** attempt)))
        raise last_exc or RuntimeError("ResilienceGate failed")
