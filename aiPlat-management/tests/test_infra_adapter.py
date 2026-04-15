"""
Tests for InfraAdapter
"""

import pytest
from management.dashboard import InfraAdapter


class TestInfraAdapter:
    """Test InfraAdapter"""
    
    @pytest.fixture
    def adapter(self):
        """Create InfraAdapter instance"""
        return InfraAdapter(endpoint="http://localhost:8001")
    
    @pytest.mark.asyncio
    async def test_get_status(self, adapter):
        """Test get_status method"""
        status = await adapter.get_status()
        
        assert status["layer"] == "infra"
        assert status["status"] in ["healthy", "degraded", "unhealthy"]
        assert "components" in status
        assert "database" in status["components"]
        assert "cache" in status["components"]
        assert "vector" in status["components"]
        assert "llm" in status["components"]
        assert "messaging" in status["components"]
        assert "storage" in status["components"]
        assert "network" in status["components"]
    
    @pytest.mark.asyncio
    async def test_health_check(self, adapter):
        """Test health_check method"""
        is_healthy = await adapter.health_check()
        assert isinstance(is_healthy, bool)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, adapter):
        """Test get_metrics method"""
        metrics = await adapter.get_metrics()
        
        assert isinstance(metrics, dict)
        assert "database" in metrics
        assert "cache" in metrics
        assert "vector" in metrics
        assert "llm" in metrics
        assert "messaging" in metrics
        assert "storage" in metrics
        assert "network" in metrics
        assert "memory" in metrics
    
    @pytest.mark.asyncio
    async def test_component_status_structure(self, adapter):
        """Test component status structure"""
        status = await adapter.get_status()
        
        for component_name, component_data in status["components"].items():
            assert "status" in component_data
            assert "message" in component_data
            assert "metrics" in component_data
            assert "details" in component_data
    
    @pytest.mark.asyncio
    async def test_database_metrics_structure(self, adapter):
        """Test database metrics structure"""
        metrics = await adapter.get_metrics()
        database_metrics = metrics["database"]
        
        assert "connections" in database_metrics
        assert "queries" in database_metrics
        assert "pool" in database_metrics
    
    @pytest.mark.asyncio
    async def test_cache_metrics_structure(self, adapter):
        """Test cache metrics structure"""
        metrics = await adapter.get_metrics()
        cache_metrics = metrics["cache"]
        
        assert "hit_rate" in cache_metrics
        assert "miss_rate" in cache_metrics
        assert "memory" in cache_metrics
        assert "keys" in cache_metrics
        assert "operations" in cache_metrics
    
    @pytest.mark.asyncio
    async def test_llm_metrics_structure(self, adapter):
        """Test LLM metrics structure"""
        metrics = await adapter.get_metrics()
        llm_metrics = metrics["llm"]
        
        assert "requests" in llm_metrics
        assert "tokens" in llm_metrics
        assert "latency" in llm_metrics
        assert "cost" in llm_metrics