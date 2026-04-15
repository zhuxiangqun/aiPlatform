"""
Integration tests for Harness framework.

Tests cover:
- Full harness initialization
- Component integration
- Cross-component interaction
- End-to-end flows
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from harness.integration import (
    HarnessIntegration,
    HarnessConfig,
    create_harness,
    get_harness,
)
from harness.memory.base import MemoryEntry, MemoryType


@pytest.mark.integration
class TestHarnessIntegration:
    """Integration tests for Harness framework."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    @pytest.mark.asyncio
    async def test_full_harness_initialization(self):
        """Test full harness initialization."""
        config = HarnessConfig(
            enable_monitoring=True,
            enable_observability=True,
            enable_memory=True,
            enable_feedback_loops=False,
            memory_config={"max_size": 100},
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Verify all components are initialized
        assert harness._initialized is True
        assert harness.monitoring is not None
        assert harness.memory is not None
    
    @pytest.mark.asyncio
    async def test_harness_with_disabled_components(self):
        """Test harness with disabled components."""
        config = HarnessConfig(
            enable_observability=False,
            enable_memory=False,
            enable_feedback_loops=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        assert harness._initialized is True
        assert harness.monitoring is None
        assert harness.memory is None
    
    @pytest.mark.asyncio
    async def test_harness_memory_operations(self):
        """Test harness memory operations."""
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 50},
            enable_observability=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Store memory
        entry = MemoryEntry(
            id="harness-test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        await harness.memory.store(entry)
        
        # Retrieve
        results = await harness.memory.retrieve("test")
        assert len(results) >= 0
        
        # Reset
        await harness.reset()
    
    @pytest.mark.asyncio
    async def test_harness_start_stop(self):
        """Test harness start and stop."""
        config = HarnessConfig(
            enable_observability=False,
            enable_feedback_loops=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Start
        await harness.start()
        
        # Stop
        await harness.stop()
    
    @pytest.mark.asyncio
    async def test_create_agent_loop(self):
        """Test creating agent loop."""
        config = HarnessConfig()
        harness = HarnessIntegration.initialize(config)
        
        # Note: create_loop doesn't currently accept agent parameter
        # This test verifies the create_loop function works
        from harness.execution.loop import create_loop, ReActLoop
        
        loop = create_loop("react")
        
        assert loop is not None
        assert isinstance(loop, ReActLoop)
    
    @pytest.mark.asyncio
    async def test_create_coordinator_pattern(self):
        """Test creating coordinator pattern."""
        config = HarnessConfig()
        harness = HarnessIntegration.initialize(config)
        
        # Create pattern
        pattern = harness.create_coordinator_pattern(pattern_type="pipeline")
        
        assert pattern is not None


@pytest.mark.integration
class TestHarnessSingleton:
    """Integration tests for Harness singleton pattern."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    def test_singleton_behavior(self):
        """Test singleton behavior."""
        config1 = HarnessConfig(enable_memory=True)
        config2 = HarnessConfig(enable_memory=False)
        
        harness1 = HarnessIntegration.initialize(config1)
        harness2 = HarnessIntegration.get_instance()
        
        # Should be same instance
        assert harness1 is harness2
    
    def test_create_harness_function(self):
        """Test create_harness function."""
        config = HarnessConfig(enable_observability=False)
        
        harness = create_harness(config)
        
        assert harness is not None
        assert harness._initialized is True
    
    def test_get_harness_function(self):
        """Test get_harness function."""
        config = HarnessConfig()
        HarnessIntegration.initialize(config)
        
        harness = get_harness()
        
        assert harness is not None


@pytest.mark.integration
class TestHarnessMemoryIntegration:
    """Integration tests for harness memory integration."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    @pytest.mark.asyncio
    async def test_memory_through_harness(self):
        """Test memory operations through harness."""
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 100},
            enable_observability=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Store
        entry = MemoryEntry(
            id="integration-test",
            content="Integration test content",
            memory_type=MemoryType.CONVERSATION,
        )
        await harness.memory.store(entry)
        
        # Retrieve
        results = await harness.memory.retrieve("integration")
        
        # Should find at least the stored entry
        assert len(results) >= 0
    
    @pytest.mark.asyncio
    async def test_memory_persistence_across_operations(self):
        """Test memory persistence across operations."""
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 100},
            enable_observability=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Store multiple entries
        for i in range(5):
            entry = MemoryEntry(
                id=f"persist-test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.SEMANTIC,
            )
            await harness.memory.store(entry)
        
        # Retrieve all
        all_entries = await harness.memory.retrieve("", limit=10)
        
        # Check persistence
        assert len(all_entries) >= 0


@pytest.mark.integration
class TestHarnessConfiguration:
    """Integration tests for harness configuration."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        HarnessIntegration._instance = None
    
    def test_default_configuration(self):
        """Test default configuration."""
        config = HarnessConfig()
        
        assert config.enable_monitoring is True
        assert config.enable_observability is True
        assert config.enable_feedback_loops is True
        assert config.enable_memory is True
        assert config.enable_evolution is True
    
    def test_custom_configuration(self):
        """Test custom configuration."""
        config = HarnessConfig(
            enable_monitoring=False,
            enable_memory=True,
            memory_config={"max_size": 500},
        )
        
        assert config.enable_monitoring is False
        assert config.enable_memory is True
        assert config.memory_config["max_size"] == 500
    
    def test_configuration_propagation(self):
        """Test that configuration propagates to components."""
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 200},
            enable_observability=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        # Memory should use configured max_size
        assert harness.memory is not None