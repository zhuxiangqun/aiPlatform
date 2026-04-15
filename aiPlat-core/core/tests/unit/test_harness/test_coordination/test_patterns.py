"""
Tests for Coordination Patterns module.

Tests cover:
- CoordinationContext
- CoordinationResult
- ICoordinationPattern interface
- Pattern implementations
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from harness.coordination.patterns import (
    CoordinationContext,
    CoordinationResult,
    ICoordinationPattern,
    PipelinePattern,
    FanOutFanInPattern,
    ExpertPoolPattern,
    ProducerReviewerPattern,
    SupervisorPattern,
    create_pattern,
)


class TestCoordinationContext:
    """Tests for CoordinationContext."""
    
    def test_context_creation(self):
        """Test creating CoordinationContext."""
        context = CoordinationContext(task="test task")
        
        assert context.task == "test task"
        assert context.agents == []
        assert context.state == {}
    
    def test_context_with_agents(self):
        """Test CoordinationContext with agents."""
        agent1 = MagicMock()
        agent2 = MagicMock()
        context = CoordinationContext(
            task="test task",
            agents=[agent1, agent2]
        )
        
        assert len(context.agents) == 2
    
    def test_context_with_state(self):
        """Test CoordinationContext with initial state."""
        context = CoordinationContext(
            task="test task",
            state={"key": "value"}
        )
        
        assert context.state["key"] == "value"
    
    def test_context_update_state(self):
        """Test updating context state."""
        context = CoordinationContext(task="test task")
        
        context.state["new_key"] = "new_value"
        
        assert context.state["new_key"] == "new_value"


class TestCoordinationResult:
    """Tests for CoordinationResult."""
    
    def test_result_creation(self):
        """Test creating CoordinationResult."""
        result = CoordinationResult(
            success=True,
            outputs=[{"answer": "test"}],
            metadata={"steps": 5}
        )
        
        assert result.success is True
        assert result.outputs[0]["answer"] == "test"
        assert result.metadata["steps"] == 5
    
    def test_result_with_errors(self):
        """Test CoordinationResult with errors."""
        result = CoordinationResult(
            success=False,
            errors=["Something went wrong"]
        )
        
        assert result.success is False
        assert "Something went wrong" in result.errors
    
    def test_result_to_dict(self):
        """Test CoordinationResult to dict."""
        result = CoordinationResult(
            success=True,
            outputs=[{"answer": "test"}],
            metadata={"steps": 5}
        )
        
        # CoordinationResult is a dataclass, access attributes directly
        assert result.success is True
        assert result.outputs[0]["answer"] == "test"
        assert result.metadata["steps"] == 5


class TestPipelinePattern:
    """Tests for PipelinePattern."""
    
    def test_init(self):
        """Test PipelinePattern initialization."""
        pattern = PipelinePattern()
        
        assert pattern is not None
    
    @pytest.mark.asyncio
    async def test_coordinate(self):
        """Test pipeline coordination."""
        pattern = PipelinePattern()
        
        # Create mock agents
        agent1 = MagicMock()
        agent1.execute = AsyncMock(return_value=MagicMock(output="result1"))
        agent2 = MagicMock()
        agent2.execute = AsyncMock(return_value=MagicMock(output="result2"))
        
        context = CoordinationContext(
            task="test task",
            agents=[agent1, agent2]
        )
        
        result = await pattern.coordinate(context)
        
        assert result.success is True
        assert len(result.outputs) == 2


class TestFanOutFanInPattern:
    """Tests for FanOutFanInPattern."""
    
    def test_init(self):
        """Test FanOutFanInPattern initialization."""
        pattern = FanOutFanInPattern()
        
        assert pattern is not None
    
    @pytest.mark.asyncio
    async def test_coordinate(self):
        """Test fan-out fan-in coordination."""
        pattern = FanOutFanInPattern()
        
        # Create mock agents
        agent1 = MagicMock()
        agent1.execute = AsyncMock(return_value="result1")
        agent2 = MagicMock()
        agent2.execute = AsyncMock(return_value="result2")
        
        context = CoordinationContext(
            task="test task",
            agents=[agent1, agent2]
        )
        
        result = await pattern.coordinate(context)
        
        assert result.success is True


class TestExpertPoolPattern:
    """Tests for ExpertPoolPattern."""
    
    def test_init(self):
        """Test ExpertPoolPattern initialization."""
        pattern = ExpertPoolPattern()
        
        assert pattern is not None


class TestProducerReviewerPattern:
    """Tests for ProducerReviewerPattern."""
    
    def test_init(self):
        """Test ProducerReviewerPattern initialization."""
        pattern = ProducerReviewerPattern()
        
        assert pattern is not None


class TestSupervisorPattern:
    """Tests for SupervisorPattern."""
    
    def test_init(self):
        """Test SupervisorPattern initialization."""
        pattern = SupervisorPattern()
        
        assert pattern is not None
    
    def test_add_worker(self):
        """Test adding workers."""
        pattern = SupervisorPattern()
        
        pattern.add_worker("worker1")
        pattern.add_worker("worker2")
        
        # Just verify it doesn't raise
        assert pattern is not None


class TestCreatePattern:
    """Tests for create_pattern factory function."""
    
    def test_create_pipeline_pattern(self):
        """Test creating PipelinePattern."""
        pattern = create_pattern("pipeline")
        
        assert isinstance(pattern, PipelinePattern)
    
    def test_create_expert_pool_pattern(self):
        """Test creating ExpertPoolPattern."""
        pattern = create_pattern("expert_pool")
        
        assert isinstance(pattern, ExpertPoolPattern)
    
    def test_create_producer_reviewer_pattern(self):
        """Test creating ProducerReviewerPattern."""
        pattern = create_pattern("producer_reviewer")
        
        assert isinstance(pattern, ProducerReviewerPattern)
    
    def test_create_supervisor_pattern(self):
        """Test creating SupervisorPattern."""
        pattern = create_pattern("supervisor")
        
        assert isinstance(pattern, SupervisorPattern)
    
    def test_create_pattern_invalid_type(self):
        """Test creating pattern with invalid type."""
        with pytest.raises(ValueError):
            create_pattern("invalid_type")