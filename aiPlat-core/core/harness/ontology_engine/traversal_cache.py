"""
Traversal Cache — LRU cache for graph traversal results.

Caches (start_entity, max_hops, direction) → TraversalResult.
Invalidated on graph mutations (add/remove entity/edge/hyperedge).
TTL-based expiry for stale entries.
"""

from __future__ import annotations

import time as _time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

CacheKey = Tuple[str, int, str]  # (start_entity, max_hops, direction)


class TraversalCache:
    """LRU cache for graph traversal with mutation-triggered invalidation."""

    def __init__(self, max_size: int = 512, ttl_seconds: float = 120.0):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[CacheKey, Tuple[float, Any]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._graph_version: int = 0  # bumped on mutation

    def get(self, start_entity: str, max_hops: int, direction: str) -> Optional[Any]:
        """Get cached result or None if miss/expired."""
        key = (start_entity, max_hops, direction)
        if key not in self._cache:
            self._misses += 1
            return None
        ts, result = self._cache[key]
        if _time.time() - ts > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end (LRU)
        self._cache.move_to_end(key)
        self._hits += 1
        return result

    def set(self, start_entity: str, max_hops: int, direction: str, result: Any) -> None:
        """Store a traversal result."""
        key = (start_entity, max_hops, direction)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (_time.time(), result)
        self._evict_if_needed()

    def invalidate(self) -> None:
        """Invalidate all cached entries (called on graph mutation)."""
        self._cache.clear()
        self._graph_version += 1

    def invalidate_entity(self, entity_id: str) -> None:
        """Invalidate entries involving a specific entity."""
        to_remove = [
            k for k in self._cache
            if k[0] == entity_id
        ]
        for k in to_remove:
            del self._cache[k]

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
            "graph_version": self._graph_version,
        }

    def _evict_if_needed(self):
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # Remove oldest (LRU)

    def __len__(self) -> int:
        return len(self._cache)


# Global singleton per domain
_cache_instances: Dict[str, TraversalCache] = {}


def get_traversal_cache(domain_id: str = "default") -> TraversalCache:
    """Get or create a TraversalCache for a domain."""
    if domain_id not in _cache_instances:
        _cache_instances[domain_id] = TraversalCache()
    return _cache_instances[domain_id]


def invalidate_all_caches():
    """Invalidate all domain caches."""
    for cache in _cache_instances.values():
        cache.invalidate()
    _cache_instances.clear()
