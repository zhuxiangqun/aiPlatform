"""
ResilienceGate (Phase 3 - minimal).

Provides a simple retry wrapper for syscalls. In later phases it will support:
- configurable retry policies
- fallback chains across engines
- circuit breakers
"""

from __future__ import annotations

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
        retry_on: Sequence[Type[BaseException]] = (asyncio.TimeoutError,),
        backoff_base_seconds: float = 0.2,
        backoff_max_seconds: float = 2.0,
    ) -> T:
        last_exc: Optional[BaseException] = None
        for attempt in range(max(0, retries) + 1):
            try:
                if timeout_seconds is not None:
                    return await asyncio.wait_for(fn(), timeout=timeout_seconds)
                return await fn()
            except BaseException as e:  # noqa: BLE001
                last_exc = e
                # Only retry on selected exceptions; otherwise fail fast.
                if not isinstance(e, tuple(retry_on)):
                    raise
                if attempt >= retries:
                    raise
                # Exponential backoff with jitter (best-effort)
                try:
                    delay = min(backoff_max_seconds, backoff_base_seconds * (2**attempt))
                    delay = max(0.0, delay + random.uniform(0.0, delay * 0.1))
                    await asyncio.sleep(delay)
                except Exception:
                    # If sleep fails, continue retrying without delay.
                    pass
        # unreachable
        raise last_exc or RuntimeError("ResilienceGate failed")
