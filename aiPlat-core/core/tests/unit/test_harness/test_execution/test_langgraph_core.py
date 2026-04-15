"""
Tests for LangGraph Core module.

Tests cover:
- GraphState
- NodeType
- NodeResult
- GraphConfig
- ExecutionTrace
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from harness.execution.langgraph.core import (
    GraphState,
    NodeType,
    NodeResult,
    GraphConfig,
    ExecutionTrace,
)


class TestGraphState:
    """Tests for GraphState TypedDict."""
    
    def test_graph_state_creation(self):
        """Test creating GraphState."""
        state: GraphState = {
            "messages": [],
            "context": {},
            "current_step": "start",
            "step_count": 0,
            "max_steps": 10,
        }
        
        assert state["messages"] == []
        assert state["context"] == {}
        assert state["current_step"] == "start"
    
    def test_graph_state_with_messages(self):
        """Test GraphState with messages."""
        state: GraphState = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            "context": {},
            "step_count": 1,
        }
        
        assert len(state["messages"]) == 2
        assert state["messages"][0]["role"] == "user"
    
    def test_graph_state_with_metadata(self):
        """Test GraphState with metadata."""
        state: GraphState = {
            "messages": [],
            "metadata": {"session_id": "123", "user_id": "user1"},
        }
        
        assert state["metadata"]["session_id"] == "123"
        assert state["metadata"]["user_id"] == "user1"


class TestNodeType:
    """Tests for NodeType enum."""
    
    def test_node_type_values(self):
        """Test NodeType enum values."""
        assert NodeType.REASON.value == "reason"
        assert NodeType.ACT.value == "act"
        assert NodeType.OBSERVE.value == "observe"
        assert NodeType.DECIDE.value == "decide"
        assert NodeType.ROUTE.value == "route"
        assert NodeType.AGGREGATE.value == "aggregate"
        assert NodeType.TRANSFORM.value == "transform"
    
    def test_node_type_count(self):
        """Test NodeType has all expected types."""
        assert len(NodeType) == 7


class TestNodeResult:
    """Tests for NodeResult dataclass."""
    
    def test_node_result_creation(self):
        """Test creating NodeResult."""
        result = NodeResult(
            success=True,
            output={"answer": "test"},
        )
        
        assert result.success is True
        assert result.output["answer"] == "test"
        assert result.next_node is None
        assert result.should_continue is True
    
    def test_node_result_with_next_node(self):
        """Test NodeResult with next_node."""
        result = NodeResult(
            success=True,
            output={"answer": "test"},
            next_node="next_step",
        )
        
        assert result.next_node == "next_step"
    
    def test_node_result_with_error(self):
        """Test NodeResult with error."""
        result = NodeResult(
            success=False,
            output=None,
            error="Something went wrong",
        )
        
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.should_continue is True
    
    def test_node_result_with_metadata(self):
        """Test NodeResult with metadata."""
        result = NodeResult(
            success=True,
            output={},
            metadata={"tokens_used": 100},
        )
        
        assert result.metadata["tokens_used"] == 100


class TestGraphConfig:
    """Tests for GraphConfig dataclass."""
    
    def test_graph_config_defaults(self):
        """Test GraphConfig default values."""
        config = GraphConfig()
        
        assert config.max_steps == 10
        assert config.timeout == 300.0
        assert config.enable_checkpoints is True
        assert config.checkpoint_interval == 5
        assert config.enable_callbacks is True
    
    def test_graph_config_custom(self):
        """Test GraphConfig with custom values."""
        config = GraphConfig(
            max_steps=20,
            timeout=600.0,
            enable_checkpoints=False,
            checkpoint_interval=10,
            enable_callbacks=False,
        )
        
        assert config.max_steps == 20
        assert config.timeout == 600.0
        assert config.enable_checkpoints is False
        assert config.checkpoint_interval == 10
        assert config.enable_callbacks is False


class TestExecutionTrace:
    """Tests for ExecutionTrace class."""
    
    def test_execution_trace_init(self):
        """Test ExecutionTrace initialization."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        assert trace.graph_id == "test-graph"
        assert trace.start_time is not None
        assert trace.end_time is None
        assert trace.nodes_executed == []
        assert trace.transitions == []
        assert trace.checkpoints == []
    
    def test_record_node(self):
        """Test recording node execution."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        result = NodeResult(success=True, output={"answer": "test"})
        trace.record_node("reason_node", result)
        
        assert len(trace.nodes_executed) == 1
        assert "reason_node" in trace.nodes_executed
        assert len(trace.transitions) == 1
        assert trace.transitions[0]["node"] == "reason_node"
        assert trace.transitions[0]["success"] is True
    
    def test_record_multiple_nodes(self):
        """Test recording multiple nodes."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        result1 = NodeResult(success=True, output={})
        result2 = NodeResult(success=True, output={})
        result3 = NodeResult(success=False, output=None, error="Failed")
        
        trace.record_node("reason", result1)
        trace.record_node("act", result2)
        trace.record_node("observe", result3)
        
        assert len(trace.nodes_executed) == 3
        assert len(trace.transitions) == 3
    
    def test_record_checkpoint(self):
        """Test recording checkpoint."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        state: GraphState = {
            "messages": [],
            "context": {"key": "value"},
            "step_count": 5,
        }
        
        trace.record_checkpoint(state)
        
        assert len(trace.checkpoints) == 1
        assert trace.checkpoints[0]["step"] == 0  # No nodes executed yet
        assert "state" in trace.checkpoints[0]
    
    def test_finalize(self):
        """Test finalizing trace."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        assert trace.end_time is None
        
        trace.finalize()
        
        assert trace.end_time is not None
    
    def test_duration_ms(self):
        """Test duration calculation."""
        trace = ExecutionTrace(graph_id="test-graph")
        trace.start_time = datetime.now() - timedelta(milliseconds=100)
        trace.finalize()
        
        duration = trace.duration_ms
        
        assert duration >= 100
    
    def test_duration_ms_not_finalized(self):
        """Test duration when not finalized."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        # Should return some duration even if not finalized
        duration = trace.duration_ms
        
        assert duration >= 0
    
    def test_success_rate_all_success(self):
        """Test success rate when all successful."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        for _ in range(5):
            result = NodeResult(success=True, output={})
            trace.record_node("node", result)
        
        assert trace.success_rate == 1.0
    
    def test_success_rate_some_failed(self):
        """Test success rate with some failures."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        result_success = NodeResult(success=True, output={})
        result_fail = NodeResult(success=False, output=None)
        
        trace.record_node("node1", result_success)
        trace.record_node("node2", result_fail)
        trace.record_node("node3", result_success)
        
        # 2 success out of 3
        assert abs(trace.success_rate - 0.6666666666666666) < 0.01
    
    def test_success_rate_empty(self):
        """Test success rate when empty."""
        trace = ExecutionTrace(graph_id="test-graph")
        
        assert trace.success_rate == 0.0