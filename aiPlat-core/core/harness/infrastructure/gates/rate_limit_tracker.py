"""
RateLimitTracker — per-model rate limit tracking with sliding window and
exponential backoff.  Aligned with hermes-agent rate_limit_tracker.py (246 lines).

Architecture: core/harness/infrastructure/gates/ — harness-level concern, no
infra dependency.  Reads rate restrictions from ClassifiedError, enforces
cooldown windows before LLM calls via ResilienceGate.

Backends:
  - InProcess (default): shared state in process memory. Single-worker OK.
  - Redis: cross-process shared state via redis.asyncio for multi-worker deploys.
"""

from __future__ import annotations
import asyncio
import json as _json
import logging
import os as _os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("aiplat.rate_limit")


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

    def to_dict(self) -> dict:
        return {
            "model": self.model, "first_hit_at": self.first_hit_at,
            "last_hit_at": self.last_hit_at, "consecutive_hits": self.consecutive_hits,
            "cooldown_until": self.cooldown_until, "window_duration": self.window_duration,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelRateLimit":
        return cls(
            model=str(d.get("model", "")), first_hit_at=float(d.get("first_hit_at", 0)),
            last_hit_at=float(d.get("last_hit_at", 0)),
            consecutive_hits=int(d.get("consecutive_hits", 0)),
            cooldown_until=float(d.get("cooldown_until", 0)),
            window_duration=float(d.get("window_duration", 10.0)),
        )


# ══════════════════════════════════════════════════════════════
# Backends
# ══════════════════════════════════════════════════════════════

class InProcessBackend:
    """Default: shared state in process memory with asyncio.Lock."""
    
    def __init__(self):
        self._table: Dict[str, ModelRateLimit] = {}
        self._lock = asyncio.Lock()

    async def get(self, model: str) -> Optional[ModelRateLimit]:
        async with self._lock:
            return self._table.get(model)

    async def set(self, entry: ModelRateLimit) -> None:
        async with self._lock:
            self._table[entry.model] = entry

    async def delete(self, model: str) -> None:
        async with self._lock:
            self._table.pop(model, None)


class RedisBackend:
    """Redis-backed shared state for multi-worker deployments.
    
    Uses redis.asyncio for non-blocking I/O.
    Configure via AIPLAT_RATE_LIMIT_REDIS_URL (default: redis://localhost:6379).
    Key prefix: 'aiplat:rl:' → aiplat:rl:deepseek-v4-pro
    Store format: JSON serialized ModelRateLimit dict.
    """
    
    def __init__(self, redis_url: str = ""):
        self._url = redis_url or _os.getenv("AIPLAT_RATE_LIMIT_REDIS_URL", "")
        self._redis = None
        self._prefix = "aiplat:rl:"
    
    async def _ensure_redis(self):
        if self._redis is not None:
            return
        if not self._url:
            raise RuntimeError("AIPLAT_RATE_LIMIT_REDIS_URL not configured")
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._url, decode_responses=False)
            await self._redis.ping()
            logger.info("RateLimitTracker: Redis backend connected (%s)", self._url)
        except ImportError:
            raise RuntimeError("redis.asyncio not installed — pip install redis")
        except Exception as e:
            self._redis = None
            raise RuntimeError(f"Redis connection failed: {e}")

    def _key(self, model: str) -> str:
        return f"{self._prefix}{model}"

    async def get(self, model: str) -> Optional[ModelRateLimit]:
        await self._ensure_redis()
        data = await self._redis.get(self._key(model))
        if data:
            return ModelRateLimit.from_dict(_json.loads(data.decode()))
        return None

    async def set(self, entry: ModelRateLimit) -> None:
        await self._ensure_redis()
        await self._redis.set(self._key(entry.model), _json.dumps(entry.to_dict()))

    async def delete(self, model: str) -> None:
        await self._ensure_redis()
        await self._redis.delete(self._key(model))


# ══════════════════════════════════════════════════════════════
# Backend selection
# ══════════════════════════════════════════════════════════════

_backend: Optional[InProcessBackend | RedisBackend] = None


def get_backend() -> InProcessBackend | RedisBackend:
    global _backend
    if _backend is None:
        redis_url = _os.getenv("AIPLAT_RATE_LIMIT_REDIS_URL", "").strip()
        if redis_url:
            try:
                _backend = RedisBackend(redis_url)
                logger.info("RateLimitTracker: using Redis backend")
            except Exception as e:
                logger.warning("RateLimitTracker: Redis backend unavailable (%s), falling back to in-process", e)
                _backend = InProcessBackend()
        else:
            _backend = InProcessBackend()
    return _backend


# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════

async def check_and_acquire(model: str) -> float:
    """Check if model is rate-limited and reserve a call slot if not.

    Returns:
        0.0 → can call immediately.
        > 0 → must wait this many seconds before calling.
    """
    backend = get_backend()
    
    if isinstance(backend, InProcessBackend):
        async with backend._lock:
            entry = backend._table.get(model)
            now = time.time()
            if entry is None or entry.cooldown_until <= now:
                return 0.0
            return entry.cooldown_until - now
    
    # Redis backend: atomic check
    entry = await backend.get(model)
    now = time.time()
    if entry is None or entry.cooldown_until <= now:
        return 0.0
    return entry.cooldown_until - now


async def record(model: str, retry_after: float = 0.0) -> None:
    """Record a rate-limit event. Called after receiving a 429 or rate limit error."""
    backend = get_backend()
    
    if isinstance(backend, InProcessBackend):
        async with backend._lock:
            await _record_impl(backend._table, model, retry_after)
        return
    
    # Redis: read → modify → write (not perfectly atomic but acceptable for rate limiting)
    entry = await backend.get(model)
    now = time.time()
    
    if entry is None:
        entry = ModelRateLimit(model=model)
    
    entry.first_hit_at = entry.first_hit_at or now
    entry.last_hit_at = now
    entry.consecutive_hits += 1
    base = entry.window_duration * 2
    entry.window_duration = min(base, 120.0)
    effective = max(0.5, min(60.0, max(retry_after, entry.window_duration)))
    entry.cooldown_until = now + effective
    
    await backend.set(entry)


async def _record_impl(table: dict, model: str, retry_after: float) -> None:
    now = time.time()
    entry = table.get(model)
    if entry is None:
        entry = ModelRateLimit(model=model)
        table[model] = entry
    entry.first_hit_at = entry.first_hit_at or now
    entry.last_hit_at = now
    entry.consecutive_hits += 1
    base = entry.window_duration * 2
    entry.window_duration = min(base, 120.0)
    effective = max(0.5, min(60.0, max(retry_after, entry.window_duration)))
    entry.cooldown_until = now + effective


async def success(model: str) -> None:
    """Record a successful call — reset consecutive hit counter and cooldown."""
    backend = get_backend()
    
    if isinstance(backend, InProcessBackend):
        async with backend._lock:
            entry = backend._table.get(model)
            if entry:
                entry.consecutive_hits = 0
                entry.window_duration = 10.0
                entry.cooldown_until = 0.0
        return
    
    entry = await backend.get(model)
    if entry:
        entry.consecutive_hits = 0
        entry.window_duration = 10.0
        entry.cooldown_until = 0.0
        await backend.set(entry)
    else:
        await backend.delete(model)


def status(model: str) -> dict:
    """Return current rate-limit status for diagnostic display (sync, in-process only)."""
    backend = get_backend()
    if isinstance(backend, InProcessBackend):
        entry = backend._table.get(model)
        if entry is None:
            return {"model": model, "limited": False, "consecutive_hits": 0}
        now = time.time()
        limited = entry.cooldown_until > now
        wait = max(0.0, entry.cooldown_until - now) if limited else 0.0
        return {
            "model": model, "limited": limited,
            "wait_seconds": round(wait, 1), "consecutive_hits": entry.consecutive_hits,
            "window_duration": round(entry.window_duration, 1),
        }
    return {"model": model, "limited": False, "consecutive_hits": 0, "backend": "redis"}
