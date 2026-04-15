"""cache 模块测试"""

import pytest
import asyncio


class TestCacheClient:
    """缓存客户端测试"""

    def test_memory_client(self):
        """测试内存缓存客户端"""
        from infra.cache.memory_client import MemoryCacheClient
        from infra.cache.schemas import CacheConfig

        config = CacheConfig()
        client = MemoryCacheClient(config)
        assert client is not None

    @pytest.mark.asyncio
    async def test_memory_set_get(self):
        """测试内存缓存设置和获取"""
        from infra.cache.memory_client import MemoryCacheClient
        from infra.cache.schemas import CacheConfig

        config = CacheConfig()
        client = MemoryCacheClient(config)
        await client.set("key", "value")
        result = await client.get("key")
        assert result == "value"
