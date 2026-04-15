"""
Trace Service - Execution Tracing and Metrics

Provides:
- Execution chain tracing
- Performance metrics collection
- Span management
- Distributed tracing support
- Trace query and analysis
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class SpanStatus(Enum):
    """Span status enumeration."""
    STARTED = "started"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class DecayType(Enum):
    """Value decay types for feedback tracking."""
    FORMAT_AFFINITY = "format_affinity"       # Decays fastest
    CAPABILITY_COMPLEMENT = "capability_complement"  # Decays medium
    FEEDBACK_QUALITY = "feedback_quality"     # Decays slowest


@dataclass
class Span:
    """
    Span - A unit of work in the trace.
    
    Attributes:
        span_id: Unique span ID
        trace_id: Trace ID this span belongs to
        parent_span_id: Parent span ID (optional)
        name: Span name
        start_time: Start timestamp
        end_time: End timestamp (optional)
        duration_ms: Duration in milliseconds
        status: Span status
        attributes: Span attributes
        events: Span events
        decay_type: Value decay type (optional)
        decay_rate: Decay rate (0-1)
        original_value: Original value before decay
        current_value: Current value after decay
    """
    span_id: str
    trace_id: str
    name: str
    parent_span_id: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.STARTED
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    decay_type: Optional[DecayType] = None
    decay_rate: float = 1.0
    original_value: Optional[float] = None
    current_value: Optional[float] = None
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add an event to this span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {}
        })
    
    def set_attribute(self, key: str, value: Any):
        """Set an attribute on this span."""
        self.attributes[key] = value
    
    def end(self, status: SpanStatus = SpanStatus.SUCCESS):
        """End this span."""
        self.end_time = datetime.utcnow()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status


@dataclass
class Trace:
    """
    Trace - A collection of spans representing an execution.
    
    Attributes:
        trace_id: Unique trace ID
        name: Trace name
        root_span_id: Root span ID
        start_time: Start timestamp
        end_time: End timestamp (optional)
        duration_ms: Total duration in milliseconds
        status: Trace status
        attributes: Trace attributes
        spans: List of spans
    """
    trace_id: str
    name: str
    root_span_id: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.STARTED
    attributes: Dict[str, Any] = field(default_factory=dict)
    spans: List[Span] = field(default_factory=list)


class TraceContext:
    """
    TraceContext - Context manager for tracing.
    
    Manages the current trace and span stack.
    """
    
    def __init__(self, trace_id: str = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self._current_trace: Optional[Trace] = None
        self._span_stack: List[Span] = []
    
    def get_current_span(self) -> Optional[Span]:
        """Get the current span."""
        return self._span_stack[-1] if self._span_stack else None


class TraceService:
    """
    Trace Service - Execution tracing and metrics.
    
    Features:
    - Trace creation and management
    - Span lifecycle management
    - Performance metrics collection
    - Trace query and analysis
    - Export to observability backends
    """
    
    def __init__(self):
        self._traces: Dict[str, Trace] = {}
        self._spans: Dict[str, Span] = {}
        self._context: Optional[TraceContext] = None
    
    async def start_trace(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Trace:
        """
        Start a new trace.
        
        Args:
            name: Trace name
            attributes: Trace attributes
            
        Returns:
            Started Trace
        """
        trace_id = str(uuid.uuid4())
        
        trace = Trace(
            trace_id=trace_id,
            name=name,
            attributes=attributes or {}
        )
        
        self._traces[trace_id] = trace
        self._context = TraceContext(trace_id)
        
        return trace
    
    async def end_trace(self, trace_id: str, status: SpanStatus = SpanStatus.SUCCESS) -> Optional[Trace]:
        """
        End a trace.
        
        Args:
            trace_id: Trace ID
            status: Trace status
            
        Returns:
            Ended Trace
        """
        trace = self._traces.get(trace_id)
        if not trace:
            return None
        
        trace.end_time = datetime.utcnow()
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        trace.status = status
        
        return trace
    
    async def start_span(
        self,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        """
        Start a new span.
        
        Args:
            trace_id: Trace ID
            name: Span name
            parent_span_id: Parent span ID (optional)
            attributes: Span attributes
            
        Returns:
            Started Span
        """
        trace = self._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")
        
        span_id = str(uuid.uuid4())
        
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            name=name,
            parent_span_id=parent_span_id,
            attributes=attributes or {}
        )
        
        trace.spans.append(span)
        self._spans[span_id] = span
        
        if not trace.root_span_id:
            trace.root_span_id = span_id
        
        return span
    
    async def end_span(self, span_id: str, status: SpanStatus = SpanStatus.SUCCESS) -> Optional[Span]:
        """
        End a span.
        
        Args:
            span_id: Span ID
            status: Span status
            
        Returns:
            Ended Span
        """
        span = self._spans.get(span_id)
        if not span:
            return None
        
        span.end(status)
        
        return span
    
    async def add_span_event(
        self,
        span_id: str,
        event_name: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add an event to a span.
        
        Args:
            span_id: Span ID
            event_name: Event name
            attributes: Event attributes
            
        Returns:
            True if successful
        """
        span = self._spans.get(span_id)
        if not span:
            return False
        
        span.add_event(event_name, attributes)
        return True
    
    async def set_span_attribute(self, span_id: str, key: str, value: Any) -> bool:
        """
        Set an attribute on a span.
        
        Args:
            span_id: Span ID
            key: Attribute key
            value: Attribute value
            
        Returns:
            True if successful
        """
        span = self._spans.get(span_id)
        if not span:
            return False
        
        span.set_attribute(key, value)
        return True
    
    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """
        Get a trace by ID.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Trace or None
        """
        return self._traces.get(trace_id)
    
    async def get_span(self, span_id: str) -> Optional[Span]:
        """
        Get a span by ID.
        
        Args:
            span_id: Span ID
            
        Returns:
            Span or None
        """
        return self._spans.get(span_id)
    
    async def list_traces(
        self,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """
        List traces.
        
        Args:
            status: Filter by status (optional)
            limit: Maximum number of traces
            
        Returns:
            List ofTrace
        """
        traces = list(self._traces.values())
        if status:
            traces = [t for t in traces if t.status == status]
        return traces[-limit:]
    
    async def get_trace_spans(self, trace_id: str) -> List[Span]:
        """
        Get all spans in a trace.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            List of Span
        """
        trace = self._traces.get(trace_id)
        return trace.spans if trace else []
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get trace statistics.
        
        Returns:
            Trace statistics
        """
        total_traces = len(self._traces)
        total_spans = len(self._spans)
        
        successful_traces = sum(1 for t in self._traces.values() if t.status == SpanStatus.SUCCESS)
        failed_traces = sum(1 for t in self._traces.values() if t.status == SpanStatus.FAILED)
        
        avg_trace_duration = 0
        if self._traces:
            durations = [t.duration_ms for t in self._traces.values() if t.duration_ms]
            avg_trace_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_traces": total_traces,
            "total_spans": total_spans,
            "successful_traces": successful_traces,
            "failed_traces": failed_traces,
            "success_rate": successful_traces / total_traces if total_traces > 0 else 0,
            "avg_trace_duration_ms": avg_trace_duration
        }
    
    async def export_trace(self, trace_id: str, format: str = "json") -> str:
        """
        Export a trace to a specific format.
        
        Args:
            trace_id: Trace ID
            format: Export format (json, otel)
            
        Returns:
            Exported trace string
        """
        trace = self._traces.get(trace_id)
        if not trace:
            return "{}"
        
        if format == "json":
            import json
            data = {
                "trace_id": trace.trace_id,
                "name": trace.name,
                "start_time": trace.start_time.isoformat(),
                "end_time": trace.end_time.isoformat() if trace.end_time else None,
                "duration_ms": trace.duration_ms,
                "status": trace.status.value,
                "attributes": trace.attributes,
                "spans": [
                    {
                        "span_id": s.span_id,
                        "name": s.name,
                        "parent_span_id": s.parent_span_id,
                        "start_time": s.start_time.isoformat(),
                        "end_time": s.end_time.isoformat() if s.end_time else None,
                        "duration_ms": s.duration_ms,
                        "status": s.status.value,
                        "attributes": s.attributes,
                        "events": s.events
                    }
                    for s in trace.spans
                ]
            }
            return json.dumps(data, indent=2)
        
        return ""
    
    async def annotate_decay(
        self,
        span_id: str,
        decay_type: DecayType,
        original_value: float
    ) -> Optional[Span]:
        """
        Annotate a span with value decay information.
        
        Args:
            span_id: Span ID
            decay_type: Type of decay
            original_value: Original value before decay
            
        Returns:
            Updated Span or None
        """
        span = self._spans.get(span_id)
        if not span:
            return None
        
        decay_rates = {
            DecayType.FORMAT_AFFINITY: 0.3,    # Fastest decay
            DecayType.CAPABILITY_COMPLEMENT: 0.7,  # Medium decay
            DecayType.FEEDBACK_QUALITY: 0.95  # Slowest decay
        }
        
        span.decay_type = decay_type
        span.decay_rate = decay_rates.get(decay_type, 1.0)
        span.original_value = original_value
        span.current_value = original_value * span.decay_rate
        
        return span
    
    async def calculate_current_value(
        self,
        span_id: str,
        days_elapsed: float
    ) -> Optional[float]:
        """
        Calculate current value of a span after time-based decay.
        
        Args:
            span_id: Span ID
            days_elapsed: Days elapsed since creation
            
        Returns:
            Current value or None
        """
        span = self._spans.get(span_id)
        if not span or not span.decay_type:
            return None
        
        base_decay = span.decay_rate
        
        daily_decay = {
            DecayType.FORMAT_AFFINITY: 0.05,  # 5% per day
            DecayType.CAPABILITY_COMPLEMENT: 0.02,  # 2% per day
            DecayType.FEEDBACK_QUALITY: 0.005  # 0.5% per day
        }
        
        daily = daily_decay.get(span.decay_type, 0.01)
        time_factor = max(0.1, 1.0 - (daily * days_elapsed))
        
        current_value = (span.original_value or 1.0) * base_decay * time_factor
        
        span.current_value = current_value
        
        return current_value
    
    async def trigger_format_conversion(
        self,
        span_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger format conversion for Format Affinity decay type.
        
        Args:
            span_id: Span ID
            
        Returns:
            Conversion result or None
        """
        span = self._spans.get(span_id)
        if not span or span.decay_type != DecayType.FORMAT_AFFINITY:
            return None
        
        span.decay_type = DecayType.FEEDBACK_QUALITY
        span.decay_rate = 0.95
        span.current_value = span.original_value or 1.0
        
        return {
            "span_id": span_id,
            "action": "format_conversion",
            "from_type": "FORMAT_AFFINITY",
            "to_type": "FEEDBACK_QUALITY",
            "new_value": span.current_value,
            "timestamp": datetime.utcnow().isoformat()
        }