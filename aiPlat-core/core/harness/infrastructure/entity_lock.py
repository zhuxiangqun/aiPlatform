"""
Entity lock abstraction — prevents concurrent execution and manages approval locks.

Two intents:
  - mutex: short-lived (5s) to prevent double-click / concurrent execution
  - stake: long-lived (3600s) for pending-approval entity locking

Supports pluggable backends: asyncio.Lock (single-process) or Redis (cluster).
"""
from __future__ import annotations

import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Literal

logger = logging.getLogger(__name__)


class EntityLock(ABC):
    """Abstract lock provider. Switch to RedisEntityLock for multi-pod deployments."""

    @abstractmethod
    async def acquire(self, lock_id: str, intent: Literal["mutex", "stake"], ttl: int = 0) -> bool:
        """Acquire a lock. ttl=0 uses default based on intent (mutex=5s, stake=3600s)."""
        ...

    @abstractmethod
    async def release(self, lock_id: str) -> None:
        """Release a lock."""
        ...

    @abstractmethod
    async def extend(self, lock_id: str, extra_ttl: int) -> bool:
        """Extend a lock's TTL. Returns False if lock doesn't exist or expired."""
        ...


class AsyncioEntityLock(EntityLock):
    """Single-process lock using asyncio.Lock + expiry timestamps."""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._expiry: Dict[str, float] = {}
        self._guard = asyncio.Lock()

    def _is_expired(self, lock_id: str) -> bool:
        exp = self._expiry.get(lock_id, 0)
        return exp > 0 and time.time() > exp

    def _cleanup(self, lock_id: str) -> None:
        if lock_id in self._locks and self._is_expired(lock_id):
            del self._locks[lock_id]
            del self._expiry[lock_id]

    async def acquire(self, lock_id: str, intent: Literal["mutex", "stake"], ttl: int = 0) -> bool:
        if ttl <= 0:
            ttl = 5 if intent == "mutex" else 3600

        async with self._guard:
            self._cleanup(lock_id)

            if lock_id in self._locks and not self._is_expired(lock_id):
                logger.debug("Lock %s already held (%.1fs remaining)", lock_id, self._expiry[lock_id] - time.time())
                return False

            # Remove stale lock if expired
            if lock_id in self._locks:
                del self._locks[lock_id]
                del self._expiry[lock_id]

            self._locks[lock_id] = asyncio.Lock()
            self._expiry[lock_id] = time.time() + ttl
            logger.debug("Lock %s acquired (intent=%s, ttl=%ds)", lock_id, intent, ttl)
            return True

    async def release(self, lock_id: str) -> None:
        async with self._guard:
            self._locks.pop(lock_id, None)
            self._expiry.pop(lock_id, None)
            logger.debug("Lock %s released", lock_id)

    async def extend(self, lock_id: str, extra_ttl: int) -> bool:
        async with self._guard:
            if lock_id not in self._locks or self._is_expired(lock_id):
                return False
            self._expiry[lock_id] = time.time() + extra_ttl
            logger.debug("Lock %s extended by %ds", lock_id, extra_ttl)
            return True
