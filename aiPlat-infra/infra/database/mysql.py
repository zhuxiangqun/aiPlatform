from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from .base import DatabaseClient
from .pool import ConnectionPool
from .schemas import DatabaseConfig, PoolStats
import aiomysql


class MySQLConnectionPool(ConnectionPool):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        pool_config = config.pool
        self._pool = None
        self._min_size = pool_config.min_size if pool_config else 5
        self._max_size = pool_config.max_size if pool_config else 20

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                db=self.config.name,
                minsize=self._min_size,
                maxsize=self._max_size,
            )
        return self._pool

    async def acquire(self):
        pool = await self._get_pool()
        return await pool.acquire()

    async def release(self, conn):
        pool = await self._get_pool()
        pool.release(conn)

    def get_stats(self) -> PoolStats:
        if self._pool is None:
            return PoolStats()
        return PoolStats(
            size=self._pool.size(),
            available=self._pool.freesize(),
            used=self._pool.size() - self._pool.freesize(),
        )

    async def resize(self, min_size: int, max_size: int) -> None:
        self._min_size = min_size
        self._max_size = max_size

    async def close(self):
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()


class MySqlClient(DatabaseClient):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[MySQLConnectionPool] = None
        self._connection = None

    async def connect(self):
        self._pool = MySQLConnectionPool(self.config)
        # 获取一个连接用于执行查询
        self._connection = await self._pool.acquire()

    async def _get_connection(self):
        if self._connection is None:
            # 如果没有连接池，使用单连接
            if self._pool is None:
                self._connection = await aiomysql.connect(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.user,
                    password=self.config.password,
                    db=self.config.name,
                )
            else:
                # 从连接池获取连接
                self._connection = await self._pool.acquire()
        return self._connection

    async def execute(self, query: str, params=None) -> List[Dict]:
        conn = await self._get_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # aiomysql支持字典或位置参数
            if params is None:
                await cursor.execute(query)
            elif isinstance(params, dict):
                await cursor.execute(query, params)
            elif isinstance(params, (tuple, list)):
                await cursor.execute(query, params)
            else:
                await cursor.execute(query)
            return await cursor.fetchall()

    async def execute_one(self, query: str, params=None) -> Optional[Dict]:
        conn = await self._get_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if params is None:
                await cursor.execute(query)
            elif isinstance(params, dict):
                await cursor.execute(query, params)
            elif isinstance(params, (tuple, list)):
                await cursor.execute(query, params)
            else:
                await cursor.execute(query)
            return await cursor.fetchone()

    async def execute_many(self, query: str, params_list=None) -> List[Any]:
        conn = await self._get_connection()
        async with conn.cursor() as cursor:
            results = []
            params_list = params_list or []
            for params in params_list:
                if params is None:
                    await cursor.execute(query)
                elif isinstance(params, dict):
                    await cursor.execute(query, params)
                elif isinstance(params, (tuple, list)):
                    await cursor.execute(query, params)
                else:
                    await cursor.execute(query)
                results.append(cursor.rowcount)
            return results

    @asynccontextmanager
    async def transaction(self):
        conn = await self._get_connection()
        async with conn.begin():
            yield conn

    async def begin(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        # 释放连接回连接池
        if self._connection and self._pool:
            try:
                await self._pool.release(self._connection)
            except Exception:
                # 如果release失败，尝试直接关闭
                if hasattr(self._connection, 'close'):
                    try:
                        self._connection.close()
                        await self._connection.wait_closed()
                    except Exception:
                        pass
            self._connection = None
        
        # 关闭连接池
        if self._pool:
            try:
                await self._pool.close()
            except Exception:
                pass
            self._pool = None

    def is_connected(self) -> bool:
        return self._connection is not None

    @property
    def pool(self) -> Optional[ConnectionPool]:
        return self._pool
