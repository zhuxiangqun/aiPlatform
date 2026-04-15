import uuid
import time
from typing import Dict, List, Optional, Any
from .base import (
    Tracer,
    Span,
    SpanContext,
    OTelMetrics,
    OTelLogger,
    Counter,
    UpDownCounter,
    Histogram,
    LogRecord,
)
from .schemas import ObservabilityConfig


class SimpleTracer(Tracer):
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self._current_span: Optional[SimpleSpan] = None

    def start_span(self, name: str, context: Optional[SpanContext] = None) -> Span:
        span = SimpleSpan(name, context or SpanContext())
        self._current_span = span
        return span

    def get_current_span(self) -> Optional[Span]:
        return self._current_span


class SimpleSpan(Span):
    def __init__(self, name: str, context: SpanContext):
        self.name = name
        self.context = context
        self._attributes: Dict[str, Any] = {}
        self._events: List[Dict] = []
        self._status_code = "ok"
        self._status_message = ""
        self._start_time = time.time()

    def set_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def add_event(self, name: str, attributes: Dict = None) -> None:
        self._events.append({"name": name, "attributes": attributes or {}})

    def set_status(self, code: str, message: str = "") -> None:
        self._status_code = code
        self._status_message = message

    def end(self) -> None:
        self._end_time = time.time()


class SimpleOTelMetrics(OTelMetrics):
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self._counters: Dict[str, Counter] = {}
        self._up_down_counters: Dict[str, UpDownCounter] = {}
        self._histograms: Dict[str, Histogram] = {}

    def counter(self, name: str, **kwargs) -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._counters[name]

    def up_down_counter(self, name: str, **kwargs) -> UpDownCounter:
        if name not in self._up_down_counters:
            self._up_down_counters[name] = UpDownCounter(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._up_down_counters[name]

    def histogram(self, name: str, **kwargs) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = Histogram(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._histograms[name]


class SimpleOTelLogger(OTelLogger):
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self._records: List[LogRecord] = []

    def log(self, record: LogRecord) -> None:
        self._records.append(record)
