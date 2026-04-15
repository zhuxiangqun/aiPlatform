"""
Enhanced Manager Tests

Tests for DatabaseManager, CacheManager, and LLMManager enhanced functionality.
"""

import pytest
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from infra.management.database.manager import DatabaseManager
from infra.management.cache.manager import CacheManager
from infra.management.llm.manager import LLMManager
from infra.management.base import Status


class TestDatabaseManager:
    """Test DatabaseManager enhanced functionality"""
    
    @pytest.mark.asyncio
    async def test_create_pool(self):
        """Test creating a database pool"""
        manager = DatabaseManager({})
        
        pool_stats = await manager.create_pool("main", {
            "pool_size": 10,
            "pool_min": 5,
            "pool_max": 20
        })
        
        assert pool_stats.pool_size == 10
        assert pool_stats.pool_min == 5
        assert pool_stats.pool_max == 20
        assert pool_stats.pool_available == 10
        assert pool_stats.pool_in_use == 0
    
    @pytest.mark.asyncio
    async def test_get_connection(self):
        """Test getting a connection from pool"""
        manager = DatabaseManager({})
        await manager.create_pool("main", {"pool_size": 5})
        
        acquired = await manager.get_connection("main")
        assert acquired is True
        
        pool = await manager.get_pool("main")
        assert pool.pool_available == 4
        assert pool.pool_in_use == 1
    
    @pytest.mark.asyncio
    async def test_release_connection(self):
        """Test releasing a connection back to pool"""
        manager = DatabaseManager({})
        await manager.create_pool("main", {"pool_size": 5})
        
        await manager.get_connection("main")
        released = await manager.release_connection("main")
        assert released is True
        
        pool = await manager.get_pool("main")
        assert pool.pool_available == 5
        assert pool.pool_in_use == 0
    
    @pytest.mark.asyncio
    async def test_record_slow_query(self):
        """Test recording slow queries"""
        manager = DatabaseManager({})
        
        await manager.record_query("SELECT * FROM users", 1500)
        await manager.record_query("SELECT * FROM orders", 2000)
        await manager.record_query("SELECT * FROM products", 500)
        
        slow_queries = await manager.get_slow_queries(limit=2)
        assert len(slow_queries) == 2
        assert slow_queries[0].duration_ms == 2000
        assert slow_queries[1].duration_ms == 1500
    
    @pytest.mark.asyncio
    async def test_pool_metrics(self):
        """Test pool metrics collection"""
        manager = DatabaseManager({})
        await manager.create_pool("main", {"pool_size": 10})
        await manager.create_pool("replica", {"pool_size": 5})
        
        metrics = await manager.get_metrics()
        
        assert len(metrics) >= 2
        
        pool_metrics = [m for m in metrics if "db.pool_size" in m.name]
        assert len(pool_metrics) == 2


class TestCacheManager:
    """Test CacheManager enhanced functionality"""
    
    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        """Test set and get operations"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("test_key", "test_value")
        value = await manager.get("test_key")
        
        assert value == "test_value"
    
    @pytest.mark.asyncio
    async def test_cache_delete(self):
        """Test cache delete operation"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("test_key", "test_value")
        deleted = await manager.delete("test_key")
        
        assert deleted is True
        
        value = await manager.get("test_key")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_cache_ttl(self):
        """Test cache TTL functionality"""
        manager = CacheManager({"backend": "memory", "default_ttl": 10})
        
        await manager.set("test_key", "test_value", ttl=10)
        
        ttl = await manager.get_ttl("test_key")
        assert ttl is not None
        assert ttl >= 0  # TTL could be very small due to timing
        assert ttl <= 10  # Should not exceed the set TTL
    
    @pytest.mark.asyncio
    async def test_cache_increment(self):
        """Test cache increment operation"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("counter", "0")
        new_value = await manager.increment("counter", 5)
        
        assert new_value == 5
    
    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("key1", "value1")
        await manager.set("key2", "value2")
        await manager.get("key1")
        await manager.get("key3")
        
        stats = await manager.get_stats()
        
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.keys == 2
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate(self):
        """Test cache hit rate calculation"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("key1", "value1")
        await manager.get("key1")
        await manager.get("key1")
        await manager.get("key2")
        
        stats = await manager.get_stats()
        
        assert stats.hit_rate == 2 / 3
    
    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Test cache clear operation"""
        manager = CacheManager({"backend": "memory"})
        
        await manager.set("key1", "value1")
        await manager.set("key2", "value2")
        
        cleared = await manager.clear()
        
        assert cleared is True
        
        stats = await manager.get_stats()
        assert stats.keys == 0


class TestLLMManagerRouting:
    """Test LLMManager routing functionality"""
    
    @pytest.mark.asyncio
    async def test_register_model(self):
        """Test registering a model"""
        manager = LLMManager({})
        
        await manager.register_model("gpt-4", {
            "enabled": True,
            "cost_per_1k_tokens": 0.03,
            "rate_limit": {"requests_per_minute": 60}
        })
        
        models = await manager.list_models()
        assert len(models) == 1
        assert models[0]["name"] == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_enable_disable_model(self):
        """Test enabling and disabling models"""
        manager = LLMManager({})
        
        await manager.register_model("gpt-3.5", {"enabled": True})
        
        success = await manager.disable_model("gpt-3.5")
        assert success is True
        
        model = await manager.get_model_config("gpt-3.5")
        assert model["enabled"] is False
        
        success = await manager.enable_model("gpt-3.5")
        assert success is True
        
        model = await manager.get_model_config("gpt-3.5")
        assert model["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_round_robin_selection(self):
        """Test round-robin model selection"""
        manager = LLMManager({"routing": {"strategy": "round_robin"}})
        
        await manager.register_model("model-1", {"enabled": True})
        await manager.register_model("model-2", {"enabled": True})
        await manager.register_model("model-3", {"enabled": True})
        
        selected1 = await manager.select_model({"prompt": "test"})
        selected2 = await manager.select_model({"prompt": "test"})
        selected3 = await manager.select_model({"prompt": "test"})
        
        assert selected1 != selected2 or selected2 != selected3
    
    @pytest.mark.asyncio
    async def test_cost_optimized_selection(self):
        """Test cost-optimized model selection"""
        manager = LLMManager({"routing": {"strategy": "cost_optimized"}})
        
        await manager.register_model("cheap-model", {
            "enabled": True,
            "cost_per_1k_tokens": 0.001
        })
        await manager.register_model("expensive-model", {
            "enabled": True,
            "cost_per_1k_tokens": 0.05
        })
        
        selected = await manager.select_model({"max_tokens": 100})
        
        assert selected == "cheap-model"
    
    @pytest.mark.asyncio
    async def test_route_request(self):
        """Test request routing"""
        manager = LLMManager({"routing": {"strategy": "round_robin"}})
        
        await manager.register_model("gpt-4", {"enabled": True})
        await manager.register_model("gpt-3.5", {"enabled": True})
        
        result = await manager.route_request({"prompt": "test", "max_tokens": 100})
        
        assert result["success"] is True
        assert "model" in result
        assert "fallback_models" in result
        assert len(result["fallback_models"]) > 0
    
    @pytest.mark.asyncio
    async def test_routing_stats(self):
        """Test getting routing statistics"""
        manager = LLMManager({"routing": {"strategy": "round_robin"}})
        
        await manager.register_model("model-1", {"enabled": True})
        await manager.register_model("model-2", {"enabled": False})
        
        stats = await manager.get_routing_stats()
        
        assert stats["strategy"] == "round_robin"
        assert stats["total_models"] == 2
        assert stats["enabled_models"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])