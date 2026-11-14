"""数据库客户端与连接池抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from .schemas import PoolStats


class DatabaseClient(ABC):
    """异步数据库客户端抽象。"""

    @abstractmethod
    async def connect(self) -> None:
        """建立连接。"""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        """执行查询并返回多行。

        Args:
            query: SQL 或查询字符串。
            params: 可选绑定参数。
        """
        pass

    @abstractmethod
    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """执行查询并返回单行。

        Args:
            query: SQL 或查询字符串。
            params: 可选绑定参数。
        """
        pass

    @abstractmethod
    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        """批量执行同一查询。

        Args:
            query: SQL 或查询字符串。
            params_list: 参数列表。
        """
        pass

    @asynccontextmanager
    @abstractmethod
    async def transaction(self):
        """事务上下文管理器。"""
        pass

    @abstractmethod
    async def begin(self) -> None:
        """开启事务。"""
        pass

    @abstractmethod
    async def commit(self) -> None:
        """提交事务。"""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """回滚事务。"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接。"""
        pass


class ConnectionPool(ABC):
    """连接池抽象（与 pool.py 对齐）。"""

    @abstractmethod
    async def acquire(self) -> Any:
        """从池中获取连接。"""
        pass

    @abstractmethod
    async def release(self, conn: Any) -> None:
        """归还连接。

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
        """关闭池。"""
        pass
