"""sqlite：模块接口。"""

import aiosqlite
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from .base import DatabaseClient
from .pool import ConnectionPool
from .schemas import DatabaseConfig, PoolStats


class SQLiteConnectionPool(ConnectionPool):
    """SQLiteConnectionPool。"""
    def __init__(self, config: DatabaseConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._connection: Optional[aiosqlite.Connection] = None

    async def _get_connection(self):
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.config.name)
        return self._connection

    async def acquire(self):
        """acquire。
        """
        return await self._get_connection()

    async def release(self, conn):
        """release。

        Args:
            conn: conn 参数。
        """
        pass

    def get_stats(self) -> PoolStats:
        """获取 stats。
        """
        return PoolStats(size=1, available=1, used=0)

    async def resize(self, min_size: int, max_size: int) -> None:
        """resize。

        Args:
            min_size: min_size 参数。
            max_size: max_size 参数。
        """
        pass

    async def close(self):
        """close。
        """
        if self._connection:
            await self._connection.close()


class SqliteClient(DatabaseClient):
    """SqliteClient。"""
    def __init__(self, config: DatabaseConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._pool: Optional[SQLiteConnectionPool] = None
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """connect。
        """
        self._connection = await aiosqlite.connect(self.config.name)
        self._pool = SQLiteConnectionPool(self.config)

    async def _get_connection(self):
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.config.name)
        return self._connection

    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        """execute。

        Args:
            query: 查询。
            params: params 参数。
        """
        conn = await self._get_connection()
        cursor = await conn.execute(query, params or {})
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """execute_one。

        Args:
            query: 查询。
            params: params 参数。
        """
        conn = await self._get_connection()
        cursor = await conn.execute(query, params or {})
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        row = await cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        """execute_many。

        Args:
            query: 查询。
            params_list: params_list 参数。
        """
        conn = await self._get_connection()
        results = []
        for params in params_list:
            await conn.execute(query, params or {})
            results.append(conn.total_changes)
        await conn.commit()
        return results

    @asynccontextmanager
    async def transaction(self):
        """transaction。
        """
        conn = await self._get_connection()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def begin(self):
        """begin。
        """
        pass

    async def commit(self):
        """commit。
        """
        if self._connection:
            await self._connection.commit()

    async def rollback(self):
        """rollback。
        """
        if self._connection:
            await self._connection.rollback()

    async def close(self):
        """close。
        """
        if self._connection:
            await self._connection.close()
        if self._pool:
            await self._pool.close()

    def is_connected(self) -> bool:
        """is_connected。
        """
        return self._connection is not None

    @property
    def pool(self) -> Optional[ConnectionPool]:
        """pool。
        """
        return self._pool
