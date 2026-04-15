"""
Tests for Feedback Loops module.

Tests cover:
- FeedbackLevel, FeedbackType enums
- FeedbackData dataclass
- LocalFeedbackLoop
- EvolutionTrigger, EvolutionEvent dataclasses
- EvolutionTriggerManager
- PushManager
- ProductionFeedbackLoop
- EvolutionEngine
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from harness.feedback_loops import (
    # Enums
    FeedbackLevel,
    FeedbackType,
    EvolutionTriggerType,
    EvolutionAction,
    # Data classes
    FeedbackData,
    EvolutionTrigger,
    EvolutionEvent,
    # Main classes
    LocalFeedbackLoop,
    PushManager,
    ProductionFeedbackLoop,
    EvolutionEngine,
    EvolutionTriggerManager,
    # Factory functions
    get_evolution_engine,
)


class TestFeedbackLevel:
    """Tests for FeedbackLevel enum."""
    
    def test_feedback_level_values(self):
        """Test FeedbackLevel enum values."""
        assert FeedbackLevel.TRACE.value == "trace"
        assert FeedbackLevel.DEBUG.value == "debug"
        assert FeedbackLevel.INFO.value == "info"
        assert FeedbackLevel.WARNING.value == "warning"
        assert FeedbackLevel.ERROR.value == "error"
    
    def test_feedback_level_count(self):
        """Test FeedbackLevel has all expected levels."""
        assert len(FeedbackLevel) == 5


class TestFeedbackType:
    """Tests for FeedbackType enum."""
    
    def test_feedback_type_values(self):
        """Test FeedbackType enum values."""
        assert FeedbackType.RESULT.value == "result"
        assert FeedbackType.ERROR.value == "error"
        assert FeedbackType.TIMEOUT.value == "timeout"
        assert FeedbackType.RETRY.value == "retry"
    
    def test_feedback_type_count(self):
        """Test FeedbackType has all expected types."""
        assert len(FeedbackType) >= 5


class TestFeedbackData:
    """Tests for FeedbackData dataclass."""
    
    def test_feedback_data_creation(self):
        """Test creating FeedbackData."""
        feedback = FeedbackData(
            level=FeedbackLevel.INFO,
            feedback_type=FeedbackType.RESULT,
            source="test_agent",
            content={"result": "success"},
        )
        
        assert feedback.level == FeedbackLevel.INFO
        assert feedback.feedback_type == FeedbackType.RESULT
        assert feedback.source == "test_agent"
        assert feedback.content["result"] == "success"
    
    def test_feedback_data_with_metadata(self):
        """Test FeedbackData with metadata."""
        feedback = FeedbackData(
            level=FeedbackLevel.WARNING,
            feedback_type=FeedbackType.ERROR,
            source="test_agent",
            content={"error": "test"},
            metadata={"component": "agent"},
        )
        
        assert feedback.metadata["component"] == "agent"


class TestEvolutionTriggerType:
    """Tests for EvolutionTriggerType enum."""
    
    def test_evolution_trigger_type_values(self):
        """Test EvolutionTriggerType enum values."""
        assert EvolutionTriggerType.ERROR_THRESHOLD.value == "error_threshold"
        assert EvolutionTriggerType.LATENCY_THRESHOLD.value == "latency_threshold"
        assert EvolutionTriggerType.QUALITY_SCORE.value == "quality_score"
    
    def test_evolution_trigger_type_count(self):
        """Test EvolutionTriggerType has all expected types."""
        assert len(EvolutionTriggerType) >= 5


class TestEvolutionAction:
    """Tests for EvolutionAction enum."""
    
    def test_evolution_action_values(self):
        """Test EvolutionAction enum values."""
        assert EvolutionAction.RESTART.value == "restart"
        assert EvolutionAction.SCALE_UP.value == "scale_up"
        assert EvolutionAction.FALLBACK.value == "fallback"


class TestEvolutionTrigger:
    """Tests for EvolutionTrigger dataclass."""
    
    def test_evolution_trigger_creation(self):
        """Test creating EvolutionTrigger."""
        trigger = EvolutionTrigger(
            trigger_type=EvolutionTriggerType.ERROR_THRESHOLD,
            condition="errors > 10",
            threshold=10.0,
            action=EvolutionAction.RESTART,
        )
        
        assert trigger.trigger_type == EvolutionTriggerType.ERROR_THRESHOLD
        assert trigger.condition == "errors > 10"
        assert trigger.threshold == 10.0
        assert trigger.action == EvolutionAction.RESTART


class TestLocalFeedbackLoop:
    """Tests for LocalFeedbackLoop."""
    
    def test_init(self):
        """Test LocalFeedbackLoop initialization."""
        loop = LocalFeedbackLoop()
        
        assert loop is not None
        assert loop.max_history == 100
    
    def test_init_custom_max_history(self):
        """Test LocalFeedbackLoop with custom max_history."""
        loop = LocalFeedbackLoop(max_history=50)
        
        assert loop.max_history == 50
    
    def test_enable_disable(self):
        """Test enable and disable."""
        loop = LocalFeedbackLoop()
        
        loop.disable()
        assert loop._enabled is False
        
        loop.enable()
        assert loop._enabled is True
    
    def test_register_handler(self):
        """Test registering handler."""
        loop = LocalFeedbackLoop()
        
        handler = MagicMock()
        loop.register_handler(handler)
        
        assert handler in loop._handlers
    
    def test_unregister_handler(self):
        """Test unregistering handler."""
        loop = LocalFeedbackLoop()
        
        handler = MagicMock()
        loop.register_handler(handler)
        loop.unregister_handler(handler)
        
        assert handler not in loop._handlers
    
    def test_emit(self):
        """Test emitting feedback."""
        loop = LocalFeedbackLoop()
        
        # Should not raise
        loop.emit(
            level=FeedbackLevel.INFO,
            feedback_type=FeedbackType.RESULT,
            source="test",
            content={"data": "test"},
        )
    
    def test_emit_when_disabled(self):
        """Test emitting feedback when disabled."""
        loop = LocalFeedbackLoop()
        loop.disable()
        
        # Should not raise and should not add to history
        loop.emit(
            level=FeedbackLevel.INFO,
            feedback_type=FeedbackType.RESULT,
            source="test",
            content={"data": "test"},
        )
    
    def test_get_history(self):
        """Test getting history."""
        loop = LocalFeedbackLoop()
        
        loop.emit(
            level=FeedbackLevel.INFO,
            feedback_type=FeedbackType.RESULT,
            source="test",
            content={"data": "test"},
        )
        
        history = loop.get_history()
        
        assert isinstance(history, list)


class TestEvolutionTriggerManager:
    """Tests for EvolutionTriggerManager."""
    
    def test_init(self):
        """Test EvolutionTriggerManager initialization."""
        manager = EvolutionTriggerManager()
        
        assert manager is not None
    
    def test_enable_disable(self):
        """Test enable and disable."""
        manager = EvolutionTriggerManager()
        
        manager.disable()
        assert manager._enabled is False
        
        manager.enable()
        assert manager._enabled is True
    
    def test_register_trigger(self):
        """Test registering trigger."""
        manager = EvolutionTriggerManager()
        
        trigger = manager.register_trigger(
            name="test_trigger",
            trigger_type=EvolutionTriggerType.ERROR_THRESHOLD,
            condition="errors > 10",
            threshold=10.0,
            action=EvolutionAction.RESTART,
        )
        
        assert trigger is not None
        assert "test_trigger" in manager._triggers


class TestPushManager:
    """Tests for PushManager."""
    
    def test_init(self):
        """Test PushManager initialization."""
        manager = PushManager()
        
        assert manager is not None
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test start and stop."""
        manager = PushManager()
        
        # Should not raise
        await manager.start()
        await manager.stop()


class TestProductionFeedbackLoop:
    """Tests for ProductionFeedbackLoop."""
    
    def test_init(self):
        """Test ProductionFeedbackLoop initialization."""
        loop = ProductionFeedbackLoop()
        
        assert loop is not None


class TestEvolutionEngine:
    """Tests for EvolutionEngine."""
    
    def test_init(self):
        """Test EvolutionEngine initialization."""
        engine = EvolutionEngine()
        
        assert engine is not None
        assert engine.manager is not None
    
    def test_register_hook(self):
        """Test registering hook."""
        engine = EvolutionEngine()
        
        def test_hook():
            pass
        
        engine.register_hook(EvolutionAction.RESTART, test_hook)
        
        assert EvolutionAction.RESTART in engine._trigger_hooks
    
    def test_setup_default_triggers(self):
        """Test setting up default triggers."""
        engine = EvolutionEngine()
        
        engine.setup_default_triggers()
        
        assert "high_error_rate" in engine.manager._triggers
        assert "high_latency" in engine.manager._triggers
        assert "low_quality" in engine.manager._triggers
        assert "high_retries" in engine.manager._triggers


class TestGetEvolutionEngine:
    """Tests for get_evolution_engine function."""
    
    def test_get_evolution_engine(self):
        """Test getting evolution engine."""
        engine = get_evolution_engine()
        
        assert engine is not None
    
    def test_get_evolution_engine_returns_same_instance(self):
        """Test get_evolution_engine returns same instance."""
        engine1 = get_evolution_engine()
        engine2 = get_evolution_engine()
        
        assert engine1 is engine2