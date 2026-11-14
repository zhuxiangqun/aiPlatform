"""
Pluggable Memory Provider ABC — extensible memory backends.

Enables swapping memory backends (SQLite → Redis → PostgreSQL)
without changing core MemoryManager logic. Each provider implements
the same interface for CRUD operations.

hermes-agent parity: agent/memory_provider.py — pluggable memory provider ABC
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class ProviderBackend(Enum):
    """ProviderBackend。"""
    SQLITE = "sqlite"
    REDIS = "redis"
    POSTGRES = "postgres"
    MEMORY = "memory"  # in-memory only (for testing)


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class MemoryRecord:
    """A single memory record."""
    key: str
    value: Any
    ttl: Optional[float] = None  # seconds, None = no expiry
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Abstract Provider ────────────────────────────────────────────────────────

class BaseMemoryProvider(ABC):
    """
    Abstract base for pluggable memory backends.

    All providers must implement CRUD + search + batch operations.
    This allows MemoryManager to work with SQLite, Redis, PostgreSQL,
    or any custom backend without code changes.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[MemoryRecord]:
        """Retrieve a memory record by key.

        Args:
            key: key 参数。
        """
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[float] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> MemoryRecord:
        """Store or update a memory record.

        Args:
            key: key 参数。
            value: value 参数。
            ttl: ttl 参数。
            metadata: metadata 参数。
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a memory record. Returns True if found and deleted.

        Args:
            key: key 参数。
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists.

        Args:
            key: key 参数。
        """
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> List[MemoryRecord]:
        """Search memory records by query (FTS or regex).

        Args:
            query: 查询。
            limit: 返回条数上限。
        """
        ...

    @abstractmethod
    async def list_keys(self, prefix: str = "", limit: int = 100) -> List[str]:
        """List keys matching a prefix.

        Args:
            prefix: prefix 参数。
            limit: 返回条数上限。
        """
        ...

    @abstractmethod
    async def batch_get(self, keys: List[str]) -> Dict[str, Optional[MemoryRecord]]:
        """Retrieve multiple records at once.

        Args:
            keys: keys 参数。
        """
        ...

    @abstractmethod
    async def batch_set(self, records: List[Tuple[str, Any, Optional[float], Optional[Dict[str, Any]]]]) -> List[MemoryRecord]:
        """Store multiple records at once. Each tuple: (key, value, ttl, metadata).

        Args:
            records: records 参数。
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired records. Returns count of removed records."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return total number of records."""
        ...

    @abstractmethod
    async def clear(self):
        """Remove all records (dangerous — use with caution)."""
        ...

    @abstractmethod
    def get_backend(self) -> ProviderBackend:
        """Return the backend type."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if the backend is healthy."""
        ...


# ── In-Memory Provider (for testing / fallback) ──────────────────────────────

class MemoryProvider(BaseMemoryProvider):
    """In-memory provider backed by a dict. Suitable for testing."""

    def __init__(self):
        """初始化。
        """
        self._store: Dict[str, MemoryRecord] = {}
        self._backend = ProviderBackend.MEMORY

    async def get(self, key: str) -> Optional[MemoryRecord]:
        """get。

        Args:
            key: key 参数。
        """
        record = self._store.get(key)
        if record and record.ttl and time.time() - record.created_at > record.ttl:
            del self._store[key]
            return None
        if record:
            record.access_count += 1
        return record

    async def set(self, key: str, value: Any, ttl: Optional[float] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> MemoryRecord:
        """set。

        Args:
            key: key 参数。
            value: value 参数。
            ttl: ttl 参数。
            metadata: metadata 参数。
        """
        record = MemoryRecord(
            key=key,
            value=value,
            ttl=ttl,
            updated_at=time.time(),
            metadata=metadata or {},
        )
        self._store[key] = record
        return record

    async def delete(self, key: str) -> bool:
        """delete。

        Args:
            key: key 参数。
        """
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """exists。

        Args:
            key: key 参数。
        """
        return key in self._store

    async def search(self, query: str, limit: int = 10) -> List[MemoryRecord]:
        """search。

        Args:
            query: 查询。
            limit: 返回条数上限。
        """
        query_lower = query.lower()
        results: List[MemoryRecord] = []
        for record in self._store.values():
            if query_lower in str(record.value).lower() or query_lower in record.key.lower():
                results.append(record)
        return results[:limit]

    async def list_keys(self, prefix: str = "", limit: int = 100) -> List[str]:
        """列出 keys。

        Args:
            prefix: prefix 参数。
            limit: 返回条数上限。
        """
        keys = [k for k in self._store if k.startswith(prefix)]
        return keys[:limit]

    async def batch_get(self, keys: List[str]) -> Dict[str, Optional[MemoryRecord]]:
        """batch_get。

        Args:
            keys: keys 参数。
        """
        return {k: await self.get(k) for k in keys}

    async def batch_set(self, records: List[Tuple[str, Any, Optional[float], Optional[Dict[str, Any]]]]) -> List[MemoryRecord]:
        """batch_set。

        Args:
            records: records 参数。
        """
        results: List[MemoryRecord] = []
        for key, value, ttl, metadata in records:
            results.append(await self.set(key, value, ttl, metadata))
        return results

    async def cleanup_expired(self) -> int:
        """cleanup_expired。
        """
        now = time.time()
        expired = [
            k for k, r in self._store.items()
            if r.ttl and now - r.created_at > r.ttl
        ]
        for k in expired:
            del self._store[k]
        return len(expired)

    async def count(self) -> int:
        """count。
        """
        return len(self._store)

    async def clear(self):
        """clear。
        """
        self._store.clear()

    def get_backend(self) -> ProviderBackend:
        """获取 backend。
        """
        return self._backend

    def is_healthy(self) -> bool:
        """is_healthy。
        """
        return True


# ── Provider Factory ─────────────────────────────────────────────────────────

_PROVIDER_REGISTRY: Dict[ProviderBackend, type] = {
    ProviderBackend.MEMORY: MemoryProvider,
}


def register_provider(backend: ProviderBackend, provider_class: type):
    """Register a custom memory provider implementation.

    Args:
        backend: backend 参数。
        provider_class: provider_class 参数。
    """
    if not issubclass(provider_class, BaseMemoryProvider):
        raise TypeError(f"{provider_class.__name__} must subclass BaseMemoryProvider")
    _PROVIDER_REGISTRY[backend] = provider_class
    logger.info("MemoryProvider: registered %s -> %s", backend.value, provider_class.__name__)


def create_memory_provider(backend: Optional[ProviderBackend] = None) -> BaseMemoryProvider:
    """Factory: create a memory provider instance.

    Args:
        backend: backend 参数。
    """
    if backend is None:
        env_backend = os.getenv("AIPLAT_MEMORY_BACKEND", "memory").lower()
        try:
            backend = ProviderBackend(env_backend)
        except ValueError:
            backend = ProviderBackend.MEMORY

    provider_class = _PROVIDER_REGISTRY.get(backend)
    if provider_class is None:
        logger.warning("MemoryProvider: backend '%s' not registered, falling back to MEMORY", backend.value)
        provider_class = MemoryProvider

    return provider_class()


# ── Global Singleton ──────────────────────────────────────────────────────────

_memory_provider: Optional[BaseMemoryProvider] = None


def get_memory_provider() -> BaseMemoryProvider:
    """Get or create the global memory provider singleton."""
    global _memory_provider
    if _memory_provider is None:
        _memory_provider = create_memory_provider()
    return _memory_provider


def reset_memory_provider():
    """Reset the global singleton (for testing)."""
    global _memory_provider
    _memory_provider = None
