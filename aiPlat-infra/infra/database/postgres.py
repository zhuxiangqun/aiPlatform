"""postgres：模块接口。"""

from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from .base import DatabaseClient
from .pool import ConnectionPool
from .schemas import DatabaseConfig, PoolStats
import logging


class PostgresConnectionPool(ConnectionPool):
    """PostgresConnectionPool。"""
    def __init__(self, config: DatabaseConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        pool_config = config.pool
        self._pool = None
        self._min_size = pool_config.min_size if pool_config else 5
        self._max_size = pool_config.max_size if pool_config else 20

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.name,
                min_size=self._min_size,
                max_size=self._max_size,
            )
        return self._pool

    async def acquire(self):
        """acquire。
        """
        pool = await self._get_pool()
        return await pool.acquire()

    async def release(self, conn):
        """release。

        Args:
            conn: conn 参数。
        """
        await conn.release()

    def get_stats(self) -> PoolStats:
        """获取 stats。
        """
        if self._pool is None:
            return PoolStats()
        return PoolStats(
            size=self._pool.get_size(),
            available=self._pool.get_idle_size(),
            used=self._pool.get_size() - self._pool.get_idle_size(),
        )

    async def resize(self, min_size: int, max_size: int) -> None:
        """resize。

        Args:
            min_size: min_size 参数。
            max_size: max_size 参数。
        """
        self._min_size = min_size
        self._max_size = max_size
        if self._pool:
            await self._pool.set_pool_size(min_size, max_size)

    async def close(self):
        """close。
        """
        if self._pool:
            await self._pool.close()


class PostgresClient(DatabaseClient):
    """PostgresClient。"""
    def __init__(self, config: DatabaseConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._pool: Optional[PostgresConnectionPool] = None
        self._connection = None

    async def connect(self):
        """connect。
        """
        self._pool = PostgresConnectionPool(self.config)
        # 获取一个连接用于执行查询
        self._connection = await self._pool.acquire()

    async def _get_connection(self):
        if self._connection is None:
            # 如果没有连接池，使用单连接
            if self._pool is None:
                import asyncpg
                self._connection = await asyncpg.connect(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.user,
                    password=self.config.password,
                    database=self.config.name,
                )
            else:
                # 从连接池获取连接
                self._connection = await self._pool.acquire()
        return self._connection

    async def execute(self, query: str, params=None) -> List[Dict]:
        """execute。

        Args:
            query: 查询。
            params: params 参数。
        """
        conn = await self._get_connection()
        # asyncpg uses positional parameters, so params can be:
        # - None: no parameters
        # - tuple/list: positional parameters
        # - dict: convert to tuple in order
        if params is None:
            rows = await conn.fetch(query)
        elif isinstance(params, dict):
            # Convert dict values to positional args
            rows = await conn.fetch(query, *params.values())
        elif isinstance(params, (tuple, list)):
            rows = await conn.fetch(query, *params)
        else:
            rows = await conn.fetch(query)
        
        # Convert asyncpg Records to list of dicts
        return [dict(row) for row in rows]

    async def execute_one(self, query: str, params=None) -> Optional[Dict]:
        """execute_one。

        Args:
            query: 查询。
            params: params 参数。
        """
        conn = await self._get_connection()
        if params is None:
            row = await conn.fetchrow(query)
        elif isinstance(params, dict):
            row = await conn.fetchrow(query, *params.values())
        elif isinstance(params, (tuple, list)):
            row = await conn.fetchrow(query, *params)
        else:
            row = await conn.fetchrow(query)
        
        return dict(row) if row else None

    async def execute_many(self, query: str, params_list=None) -> List[Any]:
        """execute_many。

        Args:
            query: 查询。
            params_list: params_list 参数。
        """
        conn = await self._get_connection()
        results = []
        params_list = params_list or []
        
        for params in params_list:
            if params is None:
                result = await conn.execute(query)
            elif isinstance(params, dict):
                result = await conn.execute(query, *params.values())
            elif isinstance(params, (tuple, list)):
                result = await conn.execute(query, *params)
            else:
                result = await conn.execute(query)
            results.append(result)
        
        return results

    @asynccontextmanager
    async def transaction(self):
        """transaction。
        """
        conn = await self._get_connection()
        async with conn.transaction():
            yield conn

    async def begin(self):
        """begin。
        """
        pass

    async def commit(self):
        """commit。
        """
        pass

    async def rollback(self):
        """rollback。
        """
        pass

    async def close(self):
        # 释放连接回连接池
        """close。
        """
        if self._connection and self._pool:
            try:
                await self._pool.release(self._connection)
            except Exception:
                # 如果release失败，尝试直接关闭
                if hasattr(self._connection, 'close'):
                    try:
                        await self._connection.close()
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
            self._connection = None
        
        # 关闭连接池
        if self._pool:
            try:
                await self._pool.close()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            self._pool = None

    def is_connected(self) -> bool:
        """is_connected。
        """
        return self._connection is not None

    @property
    def pool(self) -> Optional[ConnectionPool]:
        """pool。
        """
        return self._pool
