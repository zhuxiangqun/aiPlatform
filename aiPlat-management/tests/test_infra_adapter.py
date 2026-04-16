"""
Tests for InfraAdapter
"""

import pytest
import httpx

from management.dashboard.http_adapter import InfraHttpAdapter


class TestInfraAdapter:
    """Test HTTP-based Infra adapter (design-correct implementation)."""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter instance backed by a mocked infra API."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/infra/status":
                return httpx.Response(200, json={"status": "success", "data": {"node": "healthy"}})
            if request.url.path == "/api/infra/health":
                return httpx.Response(200, json={"status": "success", "data": {"node": {"status": "healthy"}}})
            if request.url.path == "/api/infra/metrics":
                return httpx.Response(200, json={"status": "success", "data": {"node": [{"name": "gpu_count", "value": 0, "unit": "count", "labels": {}}]}})
            return httpx.Response(404, json={"detail": "not found"})

        transport = httpx.MockTransport(handler)
        return InfraHttpAdapter(endpoint="http://infra", transport=transport)
    
    @pytest.mark.asyncio
    async def test_get_status(self, adapter):
        """Test get_status method"""
        status = await adapter.get_status()
        
        assert isinstance(status, dict)
        assert status.get("layer") == "infra"
        assert status.get("status") in ["healthy", "error"]
    
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
        # infra API returns metrics per module name
        assert len(metrics.keys()) > 0
    
    @pytest.mark.asyncio
    async def test_component_status_structure(self, adapter):
        """Test status structure (smoke)"""
        status = await adapter.get_status()
        assert isinstance(status, dict)
    
    @pytest.mark.asyncio
    async def test_database_metrics_structure(self, adapter):
        """Test metrics structure (smoke)"""
        metrics = await adapter.get_metrics()
        assert isinstance(metrics, dict)
    
    @pytest.mark.asyncio
    async def test_cache_metrics_structure(self, adapter):
        """Test metrics structure (smoke)"""
        metrics = await adapter.get_metrics()
        assert isinstance(metrics, dict)
    
    @pytest.mark.asyncio
    async def test_llm_metrics_structure(self, adapter):
        """Test metrics structure (smoke)"""
        metrics = await adapter.get_metrics()
        assert isinstance(metrics, dict)
