"""
Integration Tests for Management Module

Tests the integration between different managers.
"""

import pytest
from infra.management.manager import InfraManager
from infra.management.resources.manager import ResourcesManager
from infra.management.llm.manager import LLMManager
from infra.management.database.manager import DatabaseManager
from infra.management.monitoring.manager import MonitoringManager
from infra.management.cost.manager import CostManager


class TestInfraManager:
    """Tests for InfraManager integration"""
    
    @pytest.fixture
    def manager(self):
        """Create infrastructure manager with all components"""
        infra_manager = InfraManager()
        
        # Register resources manager
        resources_config = {
            "resources": {
                "gpu": {"provider": "nvidia", "default_quota": 1}
            }
        }
        infra_manager.register_manager("resources", ResourcesManager, resources_config)
        
        # Register LLM manager
        llm_config = {
            "llm": {
                "provider": "openai",
                "models": [{"name": "gpt-4", "provider": "openai"}]
            }
        }
        infra_manager.register_manager("llm", LLMManager, llm_config)
        
        # Register database manager
        db_config = {
            "database": {
                "postgres": {"host": "localhost", "port": 5432}
            }
        }
        infra_manager.register_manager("database", DatabaseManager, db_config)
        
        # Register monitoring manager
        monitoring_config = {
            "monitoring": {
                "enabled": True,
                "interval": 10
            }
        }
        infra_manager.register_manager("monitoring", MonitoringManager, monitoring_config)
        
        # Register cost manager
        cost_config = {
            "cost": {
                "budget": {"daily_limit": 100}
            }
        }
        infra_manager.register_manager("cost", CostManager, cost_config)
        
        return infra_manager
    
    @pytest.mark.asyncio
    async def test_manager_registration(self, manager):
        """Test manager registration"""
        managers = manager.list_managers()
        assert "resources" in managers
        assert "llm" in managers
        assert "database" in managers
        assert "monitoring" in managers
        assert "cost" in managers
    
    @pytest.mark.asyncio
    async def test_get_all_status(self, manager):
        """Test getting all module statuses"""
        all_status = await manager.get_all_status()
        
        assert isinstance(all_status, dict)
        assert len(all_status) == 5
        for name, status in all_status.items():
            assert hasattr(status, 'value')
    
    @pytest.mark.asyncio
    async def test_health_check_all(self, manager):
        """Test health check for all modules"""
        health_results = await manager.health_check_all()
        
        assert isinstance(health_results, dict)
        assert len(health_results) == 5
        for name, health in health_results.items():
            assert hasattr(health, 'status')
            assert hasattr(health, 'message')
    
    @pytest.mark.asyncio
    async def test_get_all_metrics(self, manager):
        """Test getting all metrics"""
        all_metrics = await manager.get_all_metrics()
        
        assert isinstance(all_metrics, dict)
        assert len(all_metrics) == 5
        for name, metrics in all_metrics.items():
            assert isinstance(metrics, list)
    
    @pytest.mark.asyncio
    async def test_diagnose_all(self, manager):
        """Test diagnose all modules"""
        diagnosis_results = await manager.diagnose_all()
        
        assert isinstance(diagnosis_results, dict)
        assert len(diagnosis_results) == 5
        for name, diagnosis in diagnosis_results.items():
            assert 'healthy' in diagnosis
            assert 'issues' in diagnosis
            assert 'recommendations' in diagnosis


class TestManagerInteractions:
    """Tests for manager interactions"""
    
    @pytest.fixture
    def setup_managers(self):
        """Setup multiple managers"""
        infra_manager = InfraManager()
        
        # Setup resources manager
        resources_config = {
            "resources": {
                "gpu": {"default_quota": 1, "max_quota": 4}
            }
        }
        resources_manager = ResourcesManager(resources_config)
        infra_manager.register("resources", resources_manager)
        
        # Setup LLM manager
        llm_config = {
            "llm": {
                "provider": "openai",
                "models": [{"name": "gpt-4"}],
                "cost_tracking": {"enabled": True}
            }
        }
        llm_manager = LLMManager(llm_config)
        infra_manager.register("llm", llm_manager)
        
        return infra_manager, resources_manager, llm_manager
    
    @pytest.mark.asyncio
    async def test_resources_llm_interaction(self, setup_managers):
        """Test interaction between resources and LLM managers"""
        infra_manager, resources_manager, llm_manager = setup_managers
        
        # Get resources status
        resources_status = await resources_manager.get_status()
        
        # Get LLM status
        llm_status = await llm_manager.get_status()
        
        # Both should return valid statuses
        assert hasattr(resources_status, 'value')
        assert hasattr(llm_status, 'value')
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, setup_managers):
        """Test concurrent operations across managers"""
        import asyncio
        infra_manager, resources_manager, llm_manager = setup_managers
        
        # Run concurrent operations
        results = await asyncio.gather(
            resources_manager.get_status(),
            resources_manager.health_check(),
            llm_manager.get_status(),
            llm_manager.health_check()
        )
        
        assert len(results) == 4
        for result in results:
            assert result is not None
