"""Tests for infra/cache/memory_client.py — MemoryCacheClient."""
import sys
from pathlib import Path
import os as _os; _REPO = _os.path.basename(str(Path(__file__).resolve().parents[4])); sys.path.insert(0, str(Path(__file__).resolve().parents[4] / _REPO))

import pytest
from collections import OrderedDict
from infra.cache.schemas import CacheConfig


class TestMemoryCacheConstruction:
    def test_default_construction(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        assert client._max_entries == 10000
        assert isinstance(client._cache, OrderedDict)  # bounded container
        assert client._cache is not None

    def test_custom_max_entries(self):
        from infra.cache.schemas import StrategyConfig
        cfg = CacheConfig(type="memory", strategy=StrategyConfig(max_entries=100))
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(cfg)
        assert client._max_entries == 100

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        await client.set("key1", "value1")
        result = await client.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        result = await client.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        await client.set("key1", "value1")
        assert await client.delete("key1")
        assert await client.get("key1") is None

    @pytest.mark.asyncio
    async def test_exists(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        await client.set("key1", "value1")
        assert await client.exists("key1")
        assert not await client.exists("key2")

    @pytest.mark.asyncio
    async def test_clear(self):
        from infra.cache.memory_client import MemoryCacheClient
        client = MemoryCacheClient(CacheConfig(type="memory"))
        await client.set("k1", "v1")
        await client.set("k2", "v2")
        await client.clear()
        assert await client.get("k1") is None
        assert await client.get("k2") is None
