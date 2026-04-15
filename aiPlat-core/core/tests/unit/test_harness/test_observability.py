"""
Tests for Observability module.

Tests cover:
- MetricSource, MetricCategory enums
- MetricData, AggregatedMetric dataclasses
- MetricsAggregator functionality
- MetricsCollector functionality
- EventType, EventPriority enums
- Event, EventFilter dataclasses
- EventBus subscription and publishing
"""

import pytest
from datetime import datetime

from harness.observability.metrics import (
    MetricSource,
    MetricCategory,
    MetricData,
    AggregatedMetric,
    MetricsAggregator,
    MetricsCollector,
)
from harness.observability.events import (
    EventType,
    EventPriority,
    Event,
    EventFilter,
    EventBus,
)


class TestMetricEnums:
    """Tests for metric enumerations."""
    
    def test_metric_source_values(self):
        """Test MetricSource enum values."""
        assert MetricSource.AGENT.value == "agent"
        assert MetricSource.LOOP.value == "loop"
        assert MetricSource.TOOL.value == "tool"
        assert MetricSource.SKILL.value == "skill"
    
    def test_metric_category_values(self):
        """Test MetricCategory enum values."""
        assert MetricCategory.PERFORMANCE.value == "performance"
        assert MetricCategory.QUALITY.value == "quality"
        assert MetricCategory.RELIABILITY.value == "reliability"


class TestMetricData:
    """Tests for MetricData dataclass."""
    
    def test_metric_data_creation(self):
        """Test creating MetricData."""
        metric = MetricData(
            name="latency",
            value=0.5,
            source=MetricSource.AGENT,
            category=MetricCategory.PERFORMANCE,
        )
        
        assert metric.name == "latency"
        assert metric.value == 0.5
        assert metric.source == MetricSource.AGENT
        assert metric.category == MetricCategory.PERFORMANCE
    
    def test_metric_data_with_labels(self):
        """Test MetricData with labels."""
        metric = MetricData(
            name="request_count",
            value=100,
            source=MetricSource.LOOP,
            category=MetricCategory.PERFORMANCE,
            labels={"endpoint": "/api", "method": "GET"},
        )
        
        assert metric.labels["endpoint"] == "/api"
        assert metric.labels["method"] == "GET"
    
    def test_metric_data_with_metadata(self):
        """Test MetricData with metadata."""
        metric = MetricData(
            name="memory_usage",
            value=1024.0,
            source=MetricSource.SYSTEM,
            category=MetricCategory.RESOURCE,
            metadata={"unit": "bytes"},
        )
        
        assert metric.metadata["unit"] == "bytes"


class TestAggregatedMetric:
    """Tests for AggregatedMetric dataclass."""
    
    def test_aggregated_metric_creation(self):
        """Test creating AggregatedMetric."""
        agg = AggregatedMetric(
            name="latency",
            count=100,
            sum=50.0,
            min=0.1,
            max=1.0,
            avg=0.5,
            p50=0.4,
            p95=0.9,
            p99=0.95,
        )
        
        assert agg.name == "latency"
        assert agg.count == 100
        assert agg.sum == 50.0
        assert agg.min == 0.1
        assert agg.max == 1.0
        assert agg.avg == 0.5


class TestMetricsAggregator:
    """Tests for MetricsAggregator."""
    
    def test_add_metric(self):
        """Test adding a metric."""
        aggregator = MetricsAggregator()
        
        metric = MetricData(
            name="latency",
            value=0.5,
            source=MetricSource.AGENT,
            category=MetricCategory.PERFORMANCE,
        )
        
        aggregator.add(metric)
        
        # Should not raise
    
    def test_add_multiple_metrics(self):
        """Test adding multiple metrics."""
        aggregator = MetricsAggregator()
        
        for i in range(10):
            metric = MetricData(
                name="latency",
                value=0.1 * i,
                source=MetricSource.AGENT,
                category=MetricCategory.PERFORMANCE,
            )
            aggregator.add(metric)
        
        agg = aggregator.get_aggregated("latency", MetricSource.AGENT)
        
        assert agg is not None
        assert agg.count == 10
        assert agg.min == 0.0
        assert agg.max == 0.9
    
    def test_get_aggregated_empty(self):
        """Test getting aggregated metric when empty."""
        aggregator = MetricsAggregator()
        
        agg = aggregator.get_aggregated("nonexistent", MetricSource.AGENT)
        
        assert agg is None
    
    def test_get_recent(self):
        """Test getting recent metrics."""
        aggregator = MetricsAggregator()
        
        for i in range(20):
            metric = MetricData(
                name="latency",
                value=float(i),
                source=MetricSource.AGENT,
                category=MetricCategory.PERFORMANCE,
            )
            aggregator.add(metric)
        
        recent = aggregator.get_recent("latency", MetricSource.AGENT, limit=5)
        
        assert len(recent) == 5
        # Most recent should be last
        assert recent[-1].value == 19.0


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        MetricsCollector._instance = None
    
    def test_singleton(self):
        """Test MetricsCollector is singleton."""
        instance1 = MetricsCollector.get_instance()
        instance2 = MetricsCollector.get_instance()
        
        assert instance1 is instance2
    
    def test_init(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector.get_instance()
        
        assert collector.aggregator is not None
        assert collector._counters is not None
        assert collector._gauges is not None
    
    def test_increment_counter(self):
        """Test incrementing counter."""
        collector = MetricsCollector.get_instance()
        
        collector.increment("requests", MetricSource.AGENT, 1.0)
        collector.increment("requests", MetricSource.AGENT, 1.0)
        
        # Counter should be incremented
        value = collector.get_counter("requests", MetricSource.AGENT)
        assert value == 2.0
    
    def test_set_gauge(self):
        """Test setting gauge."""
        collector = MetricsCollector.get_instance()
        
        collector.gauge("memory_usage", MetricSource.SYSTEM, 1024.0)
        
        value = collector.get_gauge("memory_usage", MetricSource.SYSTEM)
        assert value == 1024.0
    
    def test_record_timer(self):
        """Test recording timer."""
        collector = MetricsCollector.get_instance()
        
        collector.timer("latency", MetricSource.AGENT, 0.5)
        collector.timer("latency", MetricSource.AGENT, 0.7)
        
        # Verify timer was recorded
        assert "agent:latency" in collector._timers
        assert len(collector._timers["agent:latency"]) == 2
    
    def test_get_all_counters(self):
        """Test getting all counters."""
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.increment("requests", MetricSource.AGENT, 1.0)
        
        counters = collector.get_all_counters()
        
        assert "agent:requests" in counters
    
    def test_get_all_gauges(self):
        """Test getting all gauges."""
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.gauge("memory", MetricSource.SYSTEM, 1024.0)
        
        gauges = collector.get_all_gauges()
        
        assert "system:memory" in gauges
    
    def test_reset(self):
        """Test resetting metrics."""
        collector = MetricsCollector.get_instance()
        
        collector.increment("requests", MetricSource.AGENT, 1.0)
        collector.gauge("memory", MetricSource.SYSTEM, 1024.0)
        
        collector.reset()
        
        # Should be reset
        assert len(collector._counters) == 0
        assert len(collector._gauges) == 0


class TestEventType:
    """Tests for EventType enum."""
    
    def test_event_type_values(self):
        """Test EventType enum values."""
        assert EventType.AGENT_STARTED.value == "agent_started"
        assert EventType.AGENT_STOPPED.value == "agent_stopped"
        assert EventType.TOOL_INVOKED.value == "tool_invoked"
    
    def test_event_type_count(self):
        """Test EventType has all expected types."""
        assert len(EventType) >= 10


class TestEventPriority:
    """Tests for EventPriority enum."""
    
    def test_event_priority_values(self):
        """Test EventPriority enum values."""
        assert EventPriority.LOW.value == 1
        assert EventPriority.NORMAL.value == 2
        assert EventPriority.HIGH.value == 3
        assert EventPriority.CRITICAL.value == 4


class TestEvent:
    """Tests for Event dataclass."""
    
    def test_event_creation(self):
        """Test creating Event."""
        event = Event(
            type=EventType.AGENT_STARTED,
            source="agent1",
        )
        
        assert event.type == EventType.AGENT_STARTED
        assert event.source == "agent1"
        assert event.id is not None
        assert event.priority == EventPriority.NORMAL
    
    def test_event_with_data(self):
        """Test Event with data."""
        event = Event(
            type=EventType.TOOL_INVOKED,
            source="agent1",
            data={"tool": "search", "query": "test"},
        )
        
        assert event.data["tool"] == "search"
        assert event.data["query"] == "test"
    
    def test_event_with_priority(self):
        """Test Event with priority."""
        event = Event(
            type=EventType.AGENT_ERROR,
            source="agent1",
            priority=EventPriority.HIGH,
        )
        
        assert event.priority == EventPriority.HIGH


class TestEventFilter:
    """Tests for EventFilter."""
    
    def test_filter_by_type(self):
        """Test filtering by type."""
        filter_ = EventFilter(types=[EventType.AGENT_STARTED, EventType.AGENT_STOPPED])
        
        event = Event(type=EventType.AGENT_STARTED, source="agent1")
        
        assert filter_.matches(event) is True
    
    def test_filter_by_type_no_match(self):
        """Test filtering by type with no match."""
        filter_ = EventFilter(types=[EventType.TOOL_INVOKED])
        
        event = Event(type=EventType.AGENT_STARTED, source="agent1")
        
        assert filter_.matches(event) is False
    
    def test_filter_by_source(self):
        """Test filtering by source."""
        filter_ = EventFilter(sources=["agent1", "agent2"])
        
        event = Event(type=EventType.AGENT_STARTED, source="agent1")
        
        assert filter_.matches(event) is True
    
    def test_filter_by_priority(self):
        """Test filtering by priority."""
        filter_ = EventFilter(priority_min=EventPriority.HIGH)
        
        event_high = Event(type=EventType.AGENT_ERROR, source="agent1", priority=EventPriority.HIGH)
        event_low = Event(type=EventType.AGENT_STARTED, source="agent1", priority=EventPriority.LOW)
        
        assert filter_.matches(event_high) is True
        assert filter_.matches(event_low) is False


class TestEventBus:
    """Tests for EventBus."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        EventBus._instance = None
    
    def test_singleton(self):
        """Test EventBus is singleton."""
        instance1 = EventBus.get_instance()
        instance2 = EventBus.get_instance()
        
        assert instance1 is instance2
    
    def test_subscribe(self):
        """Test subscribing to events."""
        bus = EventBus.get_instance()
        
        async def handler(event: Event):
            pass
        
        bus.subscribe(EventType.AGENT_STARTED, handler)
        
        assert handler in bus._handlers[EventType.AGENT_STARTED]
    
    def test_subscribe_all(self):
        """Test subscribing to all events."""
        bus = EventBus.get_instance()
        
        async def handler(event: Event):
            pass
        
        bus.subscribe_all(handler)
        
        assert handler in bus._global_handlers
    
    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus.get_instance()
        
        async def handler(event: Event):
            pass
        
        bus.subscribe(EventType.AGENT_STARTED, handler)
        bus.unsubscribe(EventType.AGENT_STARTED, handler)
        
        assert handler not in bus._handlers[EventType.AGENT_STARTED]
    
    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publishing events."""
        bus = EventBus.get_instance()
        
        event = Event(type=EventType.AGENT_STARTED, source="agent1")
        
        # publish is async
        await bus.publish(event)