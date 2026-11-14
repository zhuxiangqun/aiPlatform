"""tracing：模块接口。"""

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
    """SimpleTracer。"""
    def __init__(self, config: ObservabilityConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._current_span: Optional[SimpleSpan] = None

    def start_span(self, name: str, context: Optional[SpanContext] = None) -> Span:
        """start_span。

        Args:
            name: name 参数。
            context: context 参数。
        """
        span = SimpleSpan(name, context or SpanContext())
        self._current_span = span
        return span

    def get_current_span(self) -> Optional[Span]:
        """获取 current_span。
        """
        return self._current_span


class SimpleSpan(Span):
    """SimpleSpan。"""
    def __init__(self, name: str, context: SpanContext):
        """初始化。

        Args:
            name: name 参数。
            context: context 参数。
        """
        self.name = name
        self.context = context
        self._attributes: Dict[str, Any] = {}
        self._events: List[Dict] = []
        self._status_code = "ok"
        self._status_message = ""
        self._start_time = time.time()

    def set_attribute(self, key: str, value: Any) -> None:
        """set_attribute。

        Args:
            key: key 参数。
            value: value 参数。
        """
        self._attributes[key] = value

    def add_event(self, name: str, attributes: Dict = None) -> None:
        """add_event。

        Args:
            name: name 参数。
            attributes: attributes 参数。
        """
        self._events.append({"name": name, "attributes": attributes or {}})

    def set_status(self, code: str, message: str = "") -> None:
        """set_status。

        Args:
            code: code 参数。
            message: message 参数。
        """
        self._status_code = code
        self._status_message = message

    def end(self) -> None:
        """end。
        """
        self._end_time = time.time()


class SimpleOTelMetrics(OTelMetrics):
    """SimpleOTelMetrics。"""
    def __init__(self, config: ObservabilityConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._counters: Dict[str, Counter] = {}
        self._up_down_counters: Dict[str, UpDownCounter] = {}
        self._histograms: Dict[str, Histogram] = {}

    def counter(self, name: str, **kwargs) -> Counter:
        """counter。

        Args:
            name: name 参数。
            kwargs: kwargs 参数。
        """
        if name not in self._counters:
            self._counters[name] = Counter(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._counters[name]

    def up_down_counter(self, name: str, **kwargs) -> UpDownCounter:
        """up_down_counter。

        Args:
            name: name 参数。
            kwargs: kwargs 参数。
        """
        if name not in self._up_down_counters:
            self._up_down_counters[name] = UpDownCounter(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._up_down_counters[name]

    def histogram(self, name: str, **kwargs) -> Histogram:
        """histogram。

        Args:
            name: name 参数。
            kwargs: kwargs 参数。
        """
        if name not in self._histograms:
            self._histograms[name] = Histogram(
                name,
                unit=kwargs.get("unit", ""),
                description=kwargs.get("description", ""),
            )
        return self._histograms[name]


class SimpleOTelLogger(OTelLogger):
    """SimpleOTelLogger。"""
    def __init__(self, config: ObservabilityConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._records: List[LogRecord] = []

    def log(self, record: LogRecord) -> None:
        """log。

        Args:
            record: record 参数。
        """
        self._records.append(record)
