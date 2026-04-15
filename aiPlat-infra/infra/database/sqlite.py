import aiosqlite
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from .base import DatabaseClient
from .pool import ConnectionPool
from .schemas import DatabaseConfig, PoolStats


class SQLiteConnectionPool(ConnectionPool):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._connection: Optional[aiosqlite.Connection] = None

    async def _get_connection(self):
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.config.name)
        return self._connection

    async def acquire(self):
        return await self._get_connection()

    async def release(self, conn):
        pass

    def get_stats(self) -> PoolStats:
        return PoolStats(size=1, available=1, used=0)

    async def resize(self, min_size: int, max_size: int) -> None:
        pass

    async def close(self):
        if self._connection:
            await self._connection.close()


class SqliteClient(DatabaseClient):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[SQLiteConnectionPool] = None
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._connection = await aiosqlite.connect(self.config.name)
        self._pool = SQLiteConnectionPool(self.config)

    async def _get_connection(self):
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.config.name)
        return self._connection

    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        conn = await self._get_connection()
        cursor = await conn.execute(query, params or {})
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        conn = await self._get_connection()
        cursor = await conn.execute(query, params or {})
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        row = await cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        conn = await self._get_connection()
        results = []
        for params in params_list:
            await conn.execute(query, params or {})
            results.append(conn.total_changes)
        await conn.commit()
        return results

    @asynccontextmanager
    async def transaction(self):
        conn = await self._get_connection()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def begin(self):
        pass

    async def commit(self):
        if self._connection:
            await self._connection.commit()

    async def rollback(self):
        if self._connection:
            await self._connection.rollback()

    async def close(self):
        if self._connection:
            await self._connection.close()
        if self._pool:
            await self._pool.close()

    def is_connected(self) -> bool:
        return self._connection is not None

    @property
    def pool(self) -> Optional[ConnectionPool]:
        return self._pool
