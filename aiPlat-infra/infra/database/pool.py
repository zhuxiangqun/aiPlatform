"""数据库连接池抽象接口。"""

from abc import ABC, abstractmethod
from typing import Any
from .schemas import PoolStats


class ConnectionPool(ABC):
    """连接池获取/释放与扩缩容抽象。"""

    @abstractmethod
    async def acquire(self) -> Any:
        """从池中获取连接。"""
        pass

    @abstractmethod
    async def release(self, conn: Any) -> None:
        """归还连接到池。

        Args:
            conn: 连接对象。
        """
        pass

    @abstractmethod
    def get_stats(self) -> PoolStats:
        """返回池统计。"""
        pass

    @abstractmethod
    async def resize(self, min_size: int, max_size: int) -> None:
        """调整池大小。

        Args:
            min_size: 最小连接数。
            max_size: 最大连接数。
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭池并释放全部连接。"""
        pass
