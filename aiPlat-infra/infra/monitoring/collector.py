import time
from typing import Dict, List, Optional
from .base import (
    MetricsCollector,
    HealthChecker,
    AlertManager,
    Counter,
    Gauge,
    Histogram,
    Metric,
    HealthStatus,
    Alert,
)
from .schemas import MonitoringConfig


class PrometheusMetricsCollector(MetricsCollector):
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._prefix = config.metrics.prefix if config.metrics else "ai_platform"

    def counter(self, name: str, **kwargs) -> Counter:
        full_name = f"{self._prefix}_{name}"
        labels = kwargs.get("labels", {})
        key = f"{full_name}_{labels}"
        if key not in self._counters:
            self._counters[key] = Counter(full_name, labels)
        return self._counters[key]

    def gauge(self, name: str, **kwargs) -> Gauge:
        full_name = f"{self._prefix}_{name}"
        labels = kwargs.get("labels", {})
        key = f"{full_name}_{labels}"
        if key not in self._gauges:
            self._gauges[key] = Gauge(full_name, labels)
        return self._gauges[key]

    def histogram(self, name: str, **kwargs) -> Histogram:
        full_name = f"{self._prefix}_{name}"
        labels = kwargs.get("labels", {})
        key = f"{full_name}_{labels}"
        if key not in self._histograms:
            self._histograms[key] = Histogram(full_name, labels)
        return self._histograms[key]

    def record(self, name: str, value: float, labels: Dict = None) -> None:
        self.gauge(name).set(value)

    def get_metrics(self) -> List[Metric]:
        metrics = []
        for c in self._counters.values():
            metrics.append(Metric(c.name, c._value, c.labels))
        for g in self._gauges.values():
            metrics.append(Metric(g.name, g._value, g.labels))
        return metrics

    def export(self) -> str:
        lines = []
        for m in self.get_metrics():
            labels = ",".join(f'{k}="{v}"' for k, v in m.labels.items())
            if labels:
                lines.append(f"{m.name}{{{labels}}} {m.value}")
            else:
                lines.append(f"{m.name} {m.value}")
        return "\n".join(lines)


class SimpleHealthChecker(HealthChecker):
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._checks: Dict[str, callable] = {}

    def check(self) -> HealthStatus:
        for name, check_fn in self._checks.items():
            try:
                if not check_fn():
                    return HealthStatus(False, f"Check {name} failed")
            except Exception as e:
                return HealthStatus(False, f"Check {name} error: {e}")
        return HealthStatus(True, "All checks passed")

    def register_check(self, name: str, check_fn) -> None:
        self._checks[name] = check_fn


class SimpleAlertManager(AlertManager):
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._active_alerts: List[Alert] = []

    def trigger(self, alert: Alert) -> None:
        alert.timestamp = time.time()
        self._active_alerts.append(alert)

    def get_active_alerts(self) -> List[Alert]:
        return self._active_alerts

    def silence(self, alert_id: str, duration: int) -> bool:
        for alert in self._active_alerts:
            if alert.id == alert_id:
                self._active_alerts.remove(alert)
                return True
        return False
