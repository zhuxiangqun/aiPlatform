import json
from typing import Optional, List, Any
from .base import CacheClient
from .schemas import CacheConfig


class RedisCacheClient(CacheClient):
    def __init__(self, config: CacheConfig):
        self.config = config
        self._client = None
        self._prefix = config.key_prefix or ""

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def connect(self):
        import redis.asyncio as redis

        pool_config = self.config.pool
        self._client = redis.Redis(
            host=self.config.host,
            port=self.config.port,
            password=self.config.password or None,
            db=self.config.db,
            max_connections=pool_config.max_connections if pool_config else 50,
            socket_timeout=pool_config.socket_timeout if pool_config else 5,
            socket_connect_timeout=pool_config.socket_connect_timeout
            if pool_config
            else 5,
            decode_responses=False,
        )

    async def get(self, key: str) -> Optional[Any]:
        if not self._client:
            await self.connect()
        value = await self._client.get(self._key(key))
        if value is None:
            return None
        try:
            return json.loads(value.decode("utf-8"))
        except:
            return value.decode("utf-8")

    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        if not self._client:
            await self.connect()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        if ttl > 0:
            return await self._client.setex(self._key(key), ttl, serialized)
        return await self._client.set(self._key(key), serialized)

    async def delete(self, key: str) -> bool:
        if not self._client:
            await self.connect()
        return await self._client.delete(self._key(key)) > 0

    async def exists(self, key: str) -> bool:
        if not self._client:
            await self.connect()
        return await self._client.exists(self._key(key)) > 0

    async def clear(self) -> None:
        if not self._client:
            await self.connect()
        await self._client.flushdb()

    async def keys(self, pattern: str) -> List[str]:
        if not self._client:
            await self.connect()
        prefix = self._prefix + pattern
        keys = []
        async for key in self._client.scan_iter(match=prefix):
            key_str = key.decode("utf-8")
            if self._prefix:
                keys.append(key_str[len(self._prefix) :])
            else:
                keys.append(key_str)
        return keys

    async def expire(self, key: str, ttl: int) -> bool:
        if not self._client:
            await self.connect()
        return await self._client.expire(self._key(key), ttl)

    async def ttl(self, key: str) -> int:
        if not self._client:
            await self.connect()
        return await self._client.ttl(self._key(key))

    async def close(self):
        if self._client:
            await self._client.close()
