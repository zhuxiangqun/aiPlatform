"""
Tests for harness integration.

Tests cover:
- HarnessConfig dataclass
- HarnessIntegration class
- create_harness function
- get_harness function
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from harness.integration import (
    HarnessConfig,
    HarnessIntegration,
    create_harness,
    get_harness,
)


class TestHarnessConfig:
    """Tests for HarnessConfig dataclass."""
    
    def test_harness_config_defaults(self):
        """Test HarnessConfig default values."""
        config = HarnessConfig()
        
        assert config.enable_monitoring is True
        assert config.enable_observability is True
        assert config.enable_feedback_loops is True
        assert config.enable_memory is True
        assert config.enable_evolution is True
        assert config.monitoring_config == {}
        assert config.memory_config == {}
        assert config.feedback_config == {}
    
    def test_harness_config_custom(self):
        """Test HarnessConfig with custom values."""
        config = HarnessConfig(
            enable_monitoring=False,
            enable_observability=False,
            enable_memory=True,
            memory_config={"max_size": 500, "ttl": 7200},
        )
        
        assert config.enable_monitoring is False
        assert config.enable_observability is False
        assert config.enable_memory is True
        assert config.memory_config["max_size"] == 500
        assert config.memory_config["ttl"] == 7200


class TestHarnessIntegration:
    """Tests for HarnessIntegration class."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    def test_init_default_config(self):
        """Test HarnessIntegration initialization with default config."""
        harness = HarnessIntegration()
        
        assert harness.config is not None
        assert harness._initialized is False
    
    def test_init_custom_config(self):
        """Test HarnessIntegration initialization with custom config."""
        config = HarnessConfig(enable_monitoring=False)
        harness = HarnessIntegration(config)
        
        assert harness.config.enable_monitoring is False
    
    def test_get_instance_singleton(self):
        """Test get_instance returns singleton."""
        instance1 = HarnessIntegration.get_instance()
        instance2 = HarnessIntegration.get_instance()
        
        assert instance1 is instance2
    
    def test_initialize_sets_up_components(self):
        """Test initialize sets up all enabled components."""
        config = HarnessConfig(
            enable_observability=True,
            enable_memory=True,
            enable_feedback_loops=True,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        assert harness._initialized is True
        assert harness._monitoring is not None
        assert harness._memory is not None
    
    def test_initialize_skips_disabled_components(self):
        """Test initialize skips disabled components."""
        config = HarnessConfig(
            enable_observability=False,
            enable_memory=False,
            enable_feedback_loops=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        assert harness._initialized is True
        assert harness._monitoring is None
        assert harness._memory is None
    
    def test_properties_return_components(self):
        """Test properties return correct components."""
        config = HarnessConfig(enable_observability=True, enable_memory=True)
        harness = HarnessIntegration.initialize(config)
        
        assert harness.monitoring is not None
        assert harness.memory is not None
    
    def test_properties_return_none_when_disabled(self):
        """Test properties return None when components disabled."""
        config = HarnessConfig(enable_observability=False)
        harness = HarnessIntegration(config)
        
        assert harness.monitoring is None
        assert harness.event_bus is None
    
    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        """Test reset clears component state."""
        config = HarnessConfig(enable_observability=True, enable_memory=True)
        harness = HarnessIntegration.initialize(config)
        
        # Reset should not raise
        await harness.reset()
    
    @pytest.mark.asyncio
    async def test_start_starts_components(self):
        """Test start starts enabled components."""
        config = HarnessConfig(enable_observability=True, enable_feedback_loops=False)
        harness = HarnessIntegration.initialize(config)
        
        # Start should not raise
        await harness.start()
    
    @pytest.mark.asyncio
    async def test_stop_stops_components(self):
        """Test stop stops enabled components."""
        config = HarnessConfig(enable_observability=True, enable_feedback_loops=False)
        harness = HarnessIntegration.initialize(config)
        
        # Stop should not raise
        await harness.stop()
    
    def test_create_agent_loop(self):
        """Test create_agent_loop creates loop."""
        config = HarnessConfig()
        harness = HarnessIntegration(config)
        
        # Mock agent
        mock_agent = MagicMock()
        
        # Create loop
        loop = harness.create_agent_loop(mock_agent, loop_type="react")
        
        # Should return a loop instances
        assert loop is not None
    
    def test_create_coordinator_pattern(self):
        """Test create_coordinator_pattern creates pattern."""
        config = HarnessConfig()
        harness = HarnessIntegration(config)
        
        pattern = harness.create_coordinator_pattern(pattern_type="pipeline")
        
        # Should return a pattern instance
        assert pattern is not None


class TestCreateHarness:
    """Tests for create_harness function."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    def test_create_harness_default_config(self):
        """Test create_harness with default config."""
        harness = create_harness()
        
        assert harness is not None
        assert harness._initialized is True
    
    def test_create_harness_custom_config(self):
        """Test create_harness with custom config."""
        config = HarnessConfig(enable_monitoring=False)
        harness = create_harness(config)
        
        assert harness is not None
        assert harness.config.enable_monitoring is False


class TestGetHarness:
    """Tests for get_harness function."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    def test_get_harness_returns_singleton(self):
        """Test get_harness returns singleton instance."""
        harness1 = get_harness()
        harness2 = get_harness()
        
        assert harness1 is harness2
    
    def test_get_harness_after_initialize(self):
        """Test get_harness returns initialized instance."""
        config = HarnessConfig(enable_memory=True)
        initialized = HarnessIntegration.initialize(config)
        
        retrieved = get_harness()
        
        assert retrieved is initialized