"""manager：模块接口。"""

from typing import Optional, List, Dict, Any, Callable
from .base import CacheClient, CacheManager as BaseCacheManager
from .schemas import CacheStats


class DefaultCacheManager(BaseCacheManager):
    """DefaultCacheManager。"""
    def __init__(self, cache_client: CacheClient):
        """初始化。

        Args:
            cache_client: cache_client 参数。
        """
        self._cache = cache_client
        self._hits = 0
        self._misses = 0

    async def get_or_set(self, key: str, factory: Callable, ttl: int) -> Any:
        """获取 or_set。

        Args:
            key: key 参数。
            factory: factory 参数。
            ttl: ttl 参数。
        """
        value = await self._cache.get(key)
        if value is not None:
            self._hits += 1
            return value
        self._misses += 1
        value = await factory() if callable(factory) else factory
        await self._cache.set(key, value, ttl=ttl)
        return value

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """获取 many。

        Args:
            keys: keys 参数。
        """
        result = {}
        for key in keys:
            value = await self._cache.get(key)
            if value is not None:
                result[key] = value
                self._hits += 1
            else:
                self._misses += 1
        return result

    async def set_many(self, items: Dict[str, Any], ttl: int) -> None:
        """set_many。

        Args:
            items: items 参数。
            ttl: ttl 参数。
        """
        for key, value in items.items():
            await self._cache.set(key, value, ttl=ttl)

    async def delete_many(self, keys: List[str]) -> None:
        """删除 many。

        Args:
            keys: keys 参数。
        """
        for key in keys:
            await self._cache.delete(key)

    async def get_stats(self) -> CacheStats:
        """获取 stats。
        """
        keys = await self._cache.keys("*") if hasattr(self._cache, "keys") else []
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            keys=len(keys),
            used_memory=0,
            hit_rate=hit_rate,
        )
