from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class MetricsCollector(ABC):
    @abstractmethod
    def counter(self, name: str, **kwargs) -> "Counter":
        pass

    @abstractmethod
    def gauge(self, name: str, **kwargs) -> "Gauge":
        pass

    @abstractmethod
    def histogram(self, name: str, **kwargs) -> "Histogram":
        pass

    @abstractmethod
    def record(self, name: str, value: float, labels: Dict = None) -> None:
        pass

    @abstractmethod
    def get_metrics(self) -> List["Metric"]:
        pass

    @abstractmethod
    def export(self) -> str:
        pass


class Counter:
    def __init__(self, name: str, labels: Dict = None):
        self.name = name
        self.labels = labels or {}
        self._value = 0

    def inc(self, value: float = 1) -> None:
        self._value += value


class Gauge:
    def __init__(self, name: str, labels: Dict = None):
        self.name = name
        self.labels = labels or {}
        self._value = 0.0

    def set(self, value: float) -> None:
        self._value = value


class Histogram:
    def __init__(self, name: str, labels: Dict = None):
        self.name = name
        self.labels = labels or {}
        self._values: List[float] = []

    def observe(self, value: float) -> None:
        self._values.append(value)


class Metric:
    def __init__(self, name: str, value: float, labels: Dict = None):
        self.name = name
        self.value = value
        self.labels = labels or {}


class HealthChecker(ABC):
    @abstractmethod
    def check(self) -> "HealthStatus":
        pass

    @abstractmethod
    def register_check(self, name: str, check_fn) -> None:
        pass


class HealthStatus:
    def __init__(self, healthy: bool, message: str = "", details: Dict = None):
        self.healthy = healthy
        self.message = message
        self.details = details or {}


class AlertManager(ABC):
    @abstractmethod
    def trigger(self, alert: "Alert") -> None:
        pass

    @abstractmethod
    def get_active_alerts(self) -> List["Alert"]:
        pass

    @abstractmethod
    def silence(self, alert_id: str, duration: int) -> bool:
        pass


class Alert:
    def __init__(self, name: str, level: str, message: str, details: Dict = None):
        self.id = f"alert-{name}"
        self.name = name
        self.level = level
        self.message = message
        self.details = details or {}
        self.timestamp = None
