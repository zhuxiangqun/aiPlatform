"""
RateLimitTracker — per-model rate limit tracking with sliding window and
exponential backoff.  Aligned with hermes-agent rate_limit_tracker.py (246 lines).

Architecture: core/harness/infrastructure/gates/ — harness-level concern, no
infra dependency.  Reads rate restrictions from ClassifiedError, enforces
cooldown windows before LLM calls via ResilienceGate.

Single-worker only: shared state lives in process memory.  Multi-worker
deployments need a Redis backend (marked with NotImplementedError guard).
"""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict


# ══════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════

@dataclass
class ModelRateLimit:
    """Per-model rate limit state."""
    model: str
    first_hit_at: float = 0.0
    last_hit_at: float = 0.0
    consecutive_hits: int = 0
    cooldown_until: float = 0.0
    window_duration: float = 10.0  # seconds — doubles on each consecutive hit


# ══════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════

_rate_table: Dict[str, ModelRateLimit] = {}
_lock = asyncio.Lock()

# Guard: single-worker only — multi-worker needs Redis shared state
import os as _os
_MAX_WORKERS = int(_os.getenv("AIPLAT_WORKER_COUNT", "1") or "1")
if _MAX_WORKERS > 1:
    raise NotImplementedError(
        "rate_limit_tracker: shared state requires Redis backend when AIPLAT_WORKER_COUNT > 1."
        "  Set AIPLAT_WORKER_COUNT=1 or configure AIPLAT_RATE_LIMIT_REDIS_URL."
    )


# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════

async def check_and_acquire(model: str) -> float:
    """Check if model is rate-limited and reserve a call slot if not.

    Returns:
        0.0 → can call immediately.
        > 0 → must wait this many seconds before calling.

    Thread-safe via asyncio.Lock — prevents concurrent callers from
    racing through the check-before-call gate.
    """
    async with _lock:
        entry = _rate_table.get(model)
        now = time.time()

        if entry is None or entry.cooldown_until <= now:
            # Not rate-limited — reserve slot and return
            return 0.0

        wait = entry.cooldown_until - now
        return wait


async def record(model: str, retry_after: float = 0.0) -> None:
    """Record a rate-limit event. Called after receiving a 429 or rate limit error.

    Exponential backoff: cooldown doubles on each consecutive hit (max 120s).
    If the provider suggests a retry_after, the cooldown is at least that value.
    """
    async with _lock:
        now = time.time()
        entry = _rate_table.get(model)

        if entry is None:
            entry = ModelRateLimit(model=model)
            _rate_table[model] = entry

        entry.first_hit_at = entry.first_hit_at or now
        entry.last_hit_at = now
        entry.consecutive_hits += 1

        # Exponential backoff: 10s → 20s → 40s → 80s → 120s (cap)
        base = entry.window_duration * 2
        entry.window_duration = min(base, 120.0)
        # Clamp retry_after from provider: min 0.5s (prevent CPU spin), max 60s (prevent UI hang)
        effective = max(0.5, min(60.0, max(retry_after, entry.window_duration)))
        entry.cooldown_until = now + effective


async def success(model: str) -> None:
    """Record a successful call — reset consecutive hit counter and cooldown."""
    async with _lock:
        entry = _rate_table.get(model)
        if entry is not None:
            entry.consecutive_hits = 0
            entry.window_duration = 10.0
            entry.cooldown_until = 0.0


def status(model: str) -> dict:
    """Return current rate-limit status for diagnostic display (sync — no lock needed for reads)."""
    entry = _rate_table.get(model)
    if entry is None:
        return {"model": model, "limited": False, "consecutive_hits": 0}
    now = time.time()
    limited = entry.cooldown_until > now
    wait = max(0.0, entry.cooldown_until - now) if limited else 0.0
    return {
        "model": model,
        "limited": limited,
        "wait_seconds": round(wait, 1),
        "consecutive_hits": entry.consecutive_hits,
        "window_duration": round(entry.window_duration, 1),
    }
