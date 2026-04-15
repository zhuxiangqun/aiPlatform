"""
Cache Manager

Manages distributed cache with support for multiple backends.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import CacheStats
from datetime import datetime
import time
import hashlib


class CacheManager(ManagementBase):
    """
    Manager for cache management.
    
    Provides cache operations with support for Redis, Memcached, and in-memory cache.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._cache_backend = config.get("backend", "memory") if config else "memory"
        self._cache_data: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, float] = {}
        self._cache_stats = CacheStats(
            hits=0,
            misses=0,
            keys=0,
            used_memory=0,
            hit_rate=0.0
        )
        self._key_prefix = config.get("key_prefix", "aiplat:") if config else "aiplat:"
        self._default_ttl = config.get("default_ttl", 3600) if config else 3600
    
    async def get_status(self) -> Status:
        """Get cache module status."""
        try:
            if self._cache_backend == "memory":
                return Status.HEALTHY
            
            if self._cache_stats.keys > 0:
                return Status.HEALTHY
            else:
                return Status.DEGRADED
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get cache metrics."""
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="cache.hits_total",
            value=self._cache_stats.hits,
            unit="count",
            timestamp=timestamp,
            labels={"backend": self._cache_backend, "module": "cache"}
        ))
        
        metrics.append(Metrics(
            name="cache.misses_total",
            value=self._cache_stats.misses,
            unit="count",
            timestamp=timestamp,
            labels={"backend": self._cache_backend, "module": "cache"}
        ))
        
        metrics.append(Metrics(
            name="cache.keys_total",
            value=self._cache_stats.keys,
            unit="count",
            timestamp=timestamp,
            labels={"backend": self._cache_backend, "module": "cache"}
        ))
        
        metrics.append(Metrics(
            name="cache.memory_bytes",
            value=self._cache_stats.used_memory,
            unit="bytes",
            timestamp=timestamp,
            labels={"backend": self._cache_backend, "module": "cache"}
        ))
        
        metrics.append(Metrics(
            name="cache.hit_rate",
            value=self._cache_stats.hit_rate,
            unit="ratio",
            timestamp=timestamp,
            labels={"backend": self._cache_backend, "module": "cache"}
        ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform cache health check."""
        try:
            status = await self.get_status()
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message=f"Cache backend {self._cache_backend} is healthy",
                    details={
                        "backend": self._cache_backend,
                        "keys": self._cache_stats.keys,
                        "hit_rate": self._cache_stats.hit_rate
                    }
                )
            elif status == Status.DEGRADED:
                return HealthStatus(
                    status=status,
                    message=f"Cache backend {self._cache_backend} is degraded",
                    details={
                        "backend": self._cache_backend,
                        "keys": self._cache_stats.keys,
                        "hit_rate": self._cache_stats.hit_rate
                    }
                )
            else:
                return HealthStatus(
                    status=status,
                    message=f"Cache backend {self._cache_backend} is unhealthy",
                    details={"backend": self._cache_backend}
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
        if "key_prefix" in config:
            self._key_prefix = config["key_prefix"]
        if "default_ttl" in config:
            self._default_ttl = config["default_ttl"]
    
    # Cache-specific methods
    
    def _make_key(self, key: str) -> str:
        """
        Create cache key with prefix.
        
        Args:
            key: Original key
        
        Returns:
            Prefixed key
        """
        return f"{self._key_prefix}{key}"
    
    def _update_hit_rate(self):
        """Update cache hit rate."""
        total = self._cache_stats.hits + self._cache_stats.misses
        if total > 0:
            self._cache_stats.hit_rate = self._cache_stats.hits / total
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_data:
            if self._cache_expiry.get(cache_key, float('inf')) > time.time():
                self._cache_stats.hits += 1
                self._update_hit_rate()
                return self._cache_data[cache_key]
        
        self._cache_stats.misses += 1
        self._update_hit_rate()
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (optional)
        
        Returns:
            True if successful
        """
        cache_key = self._make_key(key)
        ttl_value = ttl if ttl is not None else self._default_ttl
        
        self._cache_data[cache_key] = value
        self._cache_expiry[cache_key] = time.time() + ttl_value
        self._cache_stats.keys = len(self._cache_data)
        self._cache_stats.used_memory = len(str(self._cache_data))
        
        return True
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            True if deleted
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_data:
            del self._cache_data[cache_key]
            if cache_key in self._cache_expiry:
                del self._cache_expiry[cache_key]
            
            self._cache_stats.keys = len(self._cache_data)
            self._cache_stats.used_memory = len(str(self._cache_data))
            return True
        
        return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
        
        Returns:
            True if key exists
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_data:
            if self._cache_expiry.get(cache_key, float('inf')) > time.time():
                return True
        
        return False
    
    async def clear(self) -> bool:
        """
        Clear all cache entries.
        
        Returns:
            True if successful
        """
        self._cache_data = {}
        self._cache_expiry = {}
        self._cache_stats.keys = 0
        self._cache_stats.used_memory = 0
        return True
    
    async def get_stats(self) -> CacheStats:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics
        """
        self._update_hit_rate()
        return self._cache_stats
    
    async def set_ttl(self, key: str, ttl: int) -> bool:
        """
        Set TTL for existing key.
        
        Args:
            key: Cache key
            ttl: Time-to-live in seconds
        
        Returns:
            True if successful
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_data:
            self._cache_expiry[cache_key] = time.time() + ttl
            return True
        
        return False
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for key.
        
        Args:
            key: Cache key
        
        Returns:
            Remaining TTL in seconds or None
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_expiry:
            remaining = self._cache_expiry[cache_key] - time.time()
            return max(0, int(remaining))
        
        return None
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment cached value.
        
        Args:
            key: Cache key
            amount: Amount to increment
        
        Returns:
            New value or None
        """
        cache_key = self._make_key(key)
        
        if cache_key in self._cache_data:
            try:
                current_value = int(self._cache_data[cache_key])
                new_value = current_value + amount
                self._cache_data[cache_key] = new_value
                return new_value
            except (ValueError, TypeError):
                return None
        
        return None
    
    async def get_keys(self, pattern: Optional[str] = None) -> List[str]:
        """
        Get cache keys.
        
        Args:
            pattern: Key pattern (optional)
        
        Returns:
            List of keys
        """
        keys = []
        
        for key in self._cache_data.keys():
            if key.startswith(self._key_prefix):
                original_key = key[len(self._key_prefix):]
                if pattern is None or pattern in original_key:
                    keys.append(original_key)
        
        return keys
    
    async def get_memory_usage(self) -> int:
        """
        Get cache memory usage.
        
        Returns:
            Memory usage in bytes
        """
        return self._cache_stats.used_memory
    
    async def flush_expired(self) -> int:
        """
        Flush expired keys.
        
        Returns:
            Number of keys flushed
        """
        current_time = time.time()
        expired_keys = [
            key for key, expiry in self._cache_expiry.items()
            if expiry <= current_time
        ]
        
        for key in expired_keys:
            if key in self._cache_data:
                del self._cache_data[key]
            del self._cache_expiry[key]
        
        self._cache_stats.keys = len(self._cache_data)
        self._cache_stats.used_memory = len(str(self._cache_data))
        
        return len(expired_keys)