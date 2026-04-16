"""
Tests for InfraHealthChecker
"""

import pytest
import httpx

from management.diagnostics import InfraHealthChecker


class TestInfraHealthChecker:
    """Test HTTP-based InfraHealthChecker (design-correct)."""
    
    @pytest.fixture
    def checker(self):
        """Create InfraHealthChecker instance backed by mocked infra health API."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/infra/health":
                return httpx.Response(
                    200,
                    json={
                        "status": "success",
                        "data": {
                            "node": {"status": "healthy", "message": "ok", "details": {}},
                            "storage": {"status": "degraded", "message": "slow", "details": {"latency_ms": 300}},
                        },
                    },
                )
            return httpx.Response(404, json={"detail": "not found"})

        transport = httpx.MockTransport(handler)
        return InfraHealthChecker(endpoint="http://infra", transport=transport)
    
    @pytest.mark.asyncio
    async def test_check(self, checker):
        """Test check method"""
        results = await checker.check()
        
        assert isinstance(results, list)
        assert len(results) == 2
        assert {r.component for r in results} == {"node", "storage"}
    
    @pytest.mark.asyncio
    async def test_get_health(self, checker):
        """Test get_health method"""
        health = await checker.get_health()
        
        assert "layer" in health
        assert health["layer"] == "infra"
        assert "status" in health
        # node=healthy, storage=degraded => overall degraded
        assert health["status"] == "degraded"
        assert "timestamp" in health
        assert "checks" in health
        assert isinstance(health["checks"], list)
