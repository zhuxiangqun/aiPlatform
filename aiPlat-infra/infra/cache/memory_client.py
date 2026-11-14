"""memory_client：模块接口。"""

from typing import Optional, List, Dict, Any
from collections import OrderedDict
from .base import CacheClient
from .schemas import CacheConfig


class MemoryCacheClient(CacheClient):
    """MemoryCacheClient。"""
    def __init__(self, config: CacheConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        strategy = config.strategy
        # strategy is a StrategyConfig dataclass (or None) — not a dict.
        max_entries = getattr(strategy, "max_entries", 10000) if strategy else 10000
        self._cache: OrderedDict = OrderedDict()
        self._ttl: Dict[str, int] = {}
        self._max_entries = max_entries

    def _is_expired(self, key: str) -> bool:
        if key not in self._ttl:
            return False
        import time

        return time.time() > self._ttl[key]

    def _evict_if_needed(self):
        while len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)

    async def get(self, key: str) -> Optional[Any]:
        """get。

        Args:
            key: key 参数。
        """
        if key not in self._cache:
            return None
        if self._is_expired(key):
            del self._cache[key]
            del self._ttl[key]
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        """set。

        Args:
            key: key 参数。
            value: value 参数。
            ttl: ttl 参数。
        """
        self._evict_if_needed()
        self._cache[key] = value
        self._cache.move_to_end(key)
        if ttl > 0:
            import time

            self._ttl[key] = time.time() + ttl
        elif key in self._ttl:
            del self._ttl[key]
        return True

    async def delete(self, key: str) -> bool:
        """delete。

        Args:
            key: key 参数。
        """
        if key in self._cache:
            del self._cache[key]
            if key in self._ttl:
                del self._ttl[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """exists。

        Args:
            key: key 参数。
        """
        return await self.get(key) is not None

    async def clear(self) -> None:
        """clear。
        """
        self._cache.clear()
        self._ttl.clear()

    async def keys(self, pattern: str) -> List[str]:
        """keys。

        Args:
            pattern: pattern 参数。
        """
        import fnmatch

        return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]

    async def expire(self, key: str, ttl: int) -> bool:
        """expire。

        Args:
            key: key 参数。
            ttl: ttl 参数。
        """
        if key not in self._cache:
            return False
        import time

        self._ttl[key] = time.time() + ttl
        return True

    async def ttl(self, key: str) -> int:
        """ttl。

        Args:
            key: key 参数。
        """
        if key not in self._ttl:
            return -1
        import time

        remaining = self._ttl[key] - time.time()
        return int(remaining) if remaining > 0 else -2
