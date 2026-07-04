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
        # ── Structured metrics ──
        self._total_calls: int = 0
        self._total_retries: int = 0
        self._success_after_retry: int = 0
        self._final_failures: int = 0

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
        self._total_calls += 1
        last_exc: Optional[BaseException] = None
        actual_retries = 0
        for attempt in range(max(0, retries) + 1):
            try:
                if timeout_seconds is not None:
                    result = await asyncio.wait_for(fn(), timeout=timeout_seconds)
                else:
                    result = await fn()
                if actual_retries > 0:
                    self._success_after_retry += 1
                # ── Emit structured metric ──
                self._emit_metric("resilience_gate", {
                    "retries_used": actual_retries,
                    "success": True,
                    "total_backoff_ms": 0,
                })
                return result
            except Exception as e:
                last_exc = e
                actual_retries += 1
                self._total_retries += 1
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
        self._final_failures += 1
        self._emit_metric("resilience_gate", {
            "retries_used": actual_retries,
            "success": False,
            "error": str(last_exc)[:200],
        })
        raise last_exc or RuntimeError("ResilienceGate failed")

    def _emit_metric(self, metric_name: str, data: dict) -> None:
        """Best-effort structured metric emission."""
        try:
            import logging as _log
            _log.getLogger("aiplat.gate.resilience").debug(
                "%s: success=%s retries=%d",
                metric_name, data.get("success"), data.get("retries_used", 0),
            )
        except Exception:
            pass

    def get_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "total_retries": self._total_retries,
            "success_after_retry": self._success_after_retry,
            "final_failures": self._final_failures,
            "retry_success_rate": round(
                self._success_after_retry / max(self._total_retries, 1), 3
            ),
        }
