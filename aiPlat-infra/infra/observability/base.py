from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class Tracer(ABC):
    @abstractmethod
    def start_span(self, name: str, context: Optional["SpanContext"] = None) -> "Span":
        pass

    @abstractmethod
    def get_current_span(self) -> Optional["Span"]:
        pass


class Span(ABC):
    @abstractmethod
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    @abstractmethod
    def add_event(self, name: str, attributes: Dict = None) -> None:
        pass

    @abstractmethod
    def set_status(self, code: str, message: str = "") -> None:
        pass

    @abstractmethod
    def end(self) -> None:
        pass


class SpanContext:
    def __init__(self, trace_id: str = "", span_id: str = "", sampled: bool = True):
        self.trace_id = trace_id
        self.span_id = span_id
        self.sampled = sampled


class OTelMetrics(ABC):
    @abstractmethod
    def counter(self, name: str, **kwargs) -> "Counter":
        pass

    @abstractmethod
    def up_down_counter(self, name: str, **kwargs) -> "UpDownCounter":
        pass

    @abstractmethod
    def histogram(self, name: str, **kwargs) -> "Histogram":
        pass


class Counter:
    def __init__(self, name: str, unit: str = "", description: str = ""):
        self.name = name
        self.unit = unit
        self.description = description
        self._value = 0

    def add(self, value: float, attributes: Dict = None) -> None:
        self._value += value


class UpDownCounter:
    def __init__(self, name: str, unit: str = "", description: str = ""):
        self.name = name
        self.unit = unit
        self.description = description
        self._value = 0

    def add(self, value: float, attributes: Dict = None) -> None:
        self._value += value


class Histogram:
    def __init__(self, name: str, unit: str = "", description: str = ""):
        self.name = name
        self.unit = unit
        self.description = description
        self._values: List[float] = []

    def record(self, value: float, attributes: Dict = None) -> None:
        self._values.append(value)


class OTelLogger(ABC):
    @abstractmethod
    def log(self, record: "LogRecord") -> None:
        pass


class LogRecord:
    def __init__(self, message: str, severity: str = "INFO", attributes: Dict = None):
        self.message = message
        self.severity = severity
        self.attributes = attributes or {}


class Propagator(ABC):
    @abstractmethod
    def inject(self, context: SpanContext, carrier: Dict) -> None:
        pass

    @abstractmethod
    def extract(self, carrier: Dict) -> SpanContext:
        pass


class SpanExporter(ABC):
    @abstractmethod
    def export(self, spans: List[Span]) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass
