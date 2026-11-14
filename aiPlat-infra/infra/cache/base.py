"""缓存客户端与管理器抽象接口。"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from .schemas import CacheStats


class CacheClient(ABC):
    """底层缓存键值客户端抽象。"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """读取缓存值。

        Args:
            key: 缓存键。
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        """写入缓存值。

        Args:
            key: 缓存键。
            value: 缓存值。
            ttl: 过期秒数；0 表示不过期。
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存键。

        Args:
            key: 缓存键。
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """判断键是否存在。

        Args:
            key: 缓存键。
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """清空全部缓存。"""
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> List[str]:
        """按模式列出键。

        Args:
            pattern: 键匹配模式。
        """
        pass

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """设置键过期时间。

        Args:
            key: 缓存键。
            ttl: 过期秒数。
        """
        pass

    @abstractmethod
    async def ttl(self, key: str) -> int:
        """查询键剩余 TTL。

        Args:
            key: 缓存键。
        """
        pass


class CacheManager(ABC):
    """高层缓存编排（get_or_set / 批量）抽象。"""

    @abstractmethod
    async def get_or_set(self, key: str, factory: Any, ttl: int) -> Any:
        """读取缓存；缺失时调用 factory 并回填。

        Args:
            key: 缓存键。
            factory: 缺失时生成值的可调用对象。
            ttl: 过期秒数。
        """
        pass

    @abstractmethod
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """批量读取。

        Args:
            keys: 键列表。
        """
        pass

    @abstractmethod
    async def set_many(self, items: Dict[str, Any], ttl: int) -> None:
        """批量写入。

        Args:
            items: 键值 dict。
            ttl: 过期秒数。
        """
        pass

    @abstractmethod
    async def delete_many(self, keys: List[str]) -> None:
        """批量删除。

        Args:
            keys: 键列表。
        """
        pass

    @abstractmethod
    async def get_stats(self) -> CacheStats:
        """返回缓存统计。"""
        pass
