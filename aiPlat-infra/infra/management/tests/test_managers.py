"""
Tests for Management Managers
"""

import pytest
from infra.management.resources.manager import ResourcesManager
from infra.management.llm.manager import LLMManager
from infra.management.base import Status


class TestResourcesManager:
    """Tests for Resources Manager"""
    
    @pytest.fixture
    def manager(self):
        """Create resources manager"""
        config = {
            "resources": {
                "gpu": {
                    "provider": "nvidia",
                    "default_quota": 1
                }
            }
        }
        return ResourcesManager(config)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test get status"""
        status = await manager.get_status()
        assert isinstance(status, Status)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, manager):
        """Test get metrics"""
        metrics = await manager.get_metrics()
        assert isinstance(metrics, list)
        assert len(metrics) > 0
    
    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        """Test health check"""
        health = await manager.health_check()
        assert isinstance(health.status, Status)
        assert health.message
    
    @pytest.mark.asyncio
    async def test_diagnose(self, manager):
        """Test diagnose"""
        diagnosis = await manager.diagnose()
        assert isinstance(diagnosis.healthy, bool)
        assert isinstance(diagnosis.issues, list)
        assert isinstance(diagnosis.recommendations, list)


class TestLLMManager:
    """Tests for LLM Manager"""
    
    @pytest.fixture
    def manager(self):
        """Create LLM manager"""
        config = {
            "llm": {
                "provider": "openai",
                "models": [
                    {"name": "gpt-4", "provider": "openai"}
                ]
            }
        }
        return LLMManager(config)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test get status"""
        status = await manager.get_status()
        assert isinstance(status, Status)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, manager):
        """Test get metrics"""
        metrics = await manager.get_metrics()
        assert isinstance(metrics, list)
        assert len(metrics) > 0
    
    @pytest.mark.asyncio
    async def test_get_cost(self, manager):
        """Test get cost"""
        cost = await manager.get_cost()
        assert cost.date
        assert cost.total >= 0
        assert isinstance(cost.by_model, dict)
        assert isinstance(cost.by_user, dict)
    
    @pytest.mark.asyncio
    async def test_get_budget_status(self, manager):
        """Test get budget status"""
        budget = await manager.get_budget_status()
        assert budget.daily_used >= 0
        assert budget.daily_limit > 0
        assert 0 <= budget.daily_percentage <= 1
