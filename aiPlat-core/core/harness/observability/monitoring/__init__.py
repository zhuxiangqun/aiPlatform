"""__init__：模块接口。"""

from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio
import time
import logging


class MetricType(Enum):
    """MetricType。"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertLevel(Enum):
    """AlertLevel。"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MonitorStatus(Enum):
    """MonitorStatus。"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class MetricValue:
    """MetricValue。"""
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)


class MetricCollector:
    """MetricCollector。"""
    def __init__(self, name: str, metric_type: MetricType):
        """初始化。

        Args:
            name: name 参数。
            metric_type: metric_type 参数。
        """
        self.name = name
        self.metric_type = metric_type
        self.values: list[MetricValue] = []

    def record(self, value: float, labels: Optional[Dict[str, str]] = None):
        """record。

        Args:
            value: value 参数。
            labels: labels 参数。
        """
        self.values.append(MetricValue(value=value, labels=labels or {}))

    def get_latest(self) -> Optional[float]:
        """获取 latest。
        """
        return self.values[-1].value if self.values else None

    def get_average(self, window_seconds: Optional[int] = None) -> Optional[float]:
        """获取 average。

        Args:
            window_seconds: window_seconds 参数。
        """
        if not self.values:
            return None
        values = self.values
        if window_seconds:
            cutoff = datetime.now(timezone.utc).timestamp() - window_seconds
            values = [v for v in values if v.timestamp.timestamp() > cutoff]
        if not values:
            return None
        return sum(v.value for v in values) / len(values)


class MonitorTarget:
    """MonitorTarget。"""
    def __init__(
        self,
        name: str,
        check_fn: Callable[[], bool],
        interval: float = 60.0,
        timeout: float = 5.0,
    ):
        """初始化。

        Args:
            name: name 参数。
            check_fn: check_fn 参数。
            interval: interval 参数。
            timeout: 超时秒数。
        """
        self.name = name
        self.check_fn = check_fn
        self.interval = interval
        self.timeout = timeout
        self.status = MonitorStatus.HEALTHY
        self.last_check = datetime.now(timezone.utc)
        self.last_error: Optional[str] = None

    async def check(self) -> MonitorStatus:
        """check。
        """
        try:
            if asyncio.iscoroutinefunction(self.check_fn):
                result = await asyncio.wait_for(self.check_fn(), timeout=self.timeout)
            else:
                result = self.check_fn()
            self.status = MonitorStatus.HEALTHY if result else MonitorStatus.UNHEALTHY
            self.last_error = None
        except asyncio.TimeoutError:
            self.status = MonitorStatus.UNHEALTHY
            self.last_error = "Check timeout"
        except Exception as e:
            self.status = MonitorStatus.UNHEALTHY
            self.last_error = str(e)
        self.last_check = datetime.now(timezone.utc)
        return self.status


@dataclass
class Alert:
    """Alert。"""
    level: AlertLevel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MonitoringSystem:
    """MonitoringSystem。"""
    _instance: Optional["MonitoringSystem"] = None

    def __init__(self):
        """初始化。
        """
        self.metrics: Dict[str, MetricCollector] = {}
        self.targets: Dict[str, MonitorTarget] = {}
        self.alert_handlers: list[Callable[[Alert], None]] = []
        self._running = False

    @classmethod
    def get_instance(cls) -> "MonitoringSystem":
        """获取 instance。
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_metric(
        self, name: str, metric_type: MetricType = MetricType.COUNTER
    ) -> MetricCollector:
        """register_metric。

        Args:
            name: name 参数。
            metric_type: metric_type 参数。
        """
        if name not in self.metrics:
            self.metrics[name] = MetricCollector(name, metric_type)
        return self.metrics[name]

    def record(self, metric: str, value: float, labels: Optional[Dict[str, str]] = None):
        """record。

        Args:
            metric: metric 参数。
            value: value 参数。
            labels: labels 参数。
        """
        if metric not in self.metrics:
            self.register_metric(metric)
        self.metrics[metric].record(value, labels)

    def increment(self, metric: str, labels: Optional[Dict[str, str]] = None):
        """increment。

        Args:
            metric: metric 参数。
            labels: labels 参数。
        """
        current = self.metrics.get(metric)
        if current and current.metric_type == MetricType.COUNTER:
            current.record(current.get_latest() or 0, labels)
        self.record(metric, 1, labels)

    def gauge(self, metric: str, value: float, labels: Optional[Dict[str, str]] = None):
        """gauge。

        Args:
            metric: metric 参数。
            value: value 参数。
            labels: labels 参数。
        """
        self.record(metric, value, labels)

    def timing(self, metric: str, duration_ms: float, labels: Optional[Dict[str, str]] = None):
        """timing。

        Args:
            metric: metric 参数。
            duration_ms: duration_ms 参数。
            labels: labels 参数。
        """
        self.record(metric, duration_ms, labels)

    def register_target(
        self,
        name: str,
        check_fn: Callable[[], bool],
        interval: float = 60.0,
        timeout: float = 5.0,
    ):
        """register_target。

        Args:
            name: name 参数。
            check_fn: check_fn 参数。
            interval: interval 参数。
            timeout: 超时秒数。
        """
        self.targets[name] = MonitorTarget(name, check_fn, interval, timeout)

    def register_alert_handler(self, handler: Callable[[Alert], None]):
        """register_alert_handler。

        Args:
            handler: handler 参数。
        """
        self.alert_handlers.append(handler)

    def emit_alert(self, level: AlertLevel, message: str, source: str, **metadata):
        """emit_alert。

        Args:
            level: level 参数。
            message: message 参数。
            source: source 参数。
            metadata: metadata 参数。
        """
        alert = Alert(level=level, message=message, source=source, metadata=metadata)
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    async def start_monitoring(self):
        """start_monitoring。
        """
        self._running = True
        while self._running:
            for target in self.targets.values():
                status = await target.check()
                if status == MonitorStatus.UNHEALTHY:
                    self.emit_alert(
                        AlertLevel.WARNING,
                        f"Target {target.name} is unhealthy: {target.last_error}",
                        "monitoring",
                    )
                elif status == MonitorStatus.DEGRADED:
                    self.emit_alert(
                        AlertLevel.INFO,
                        f"Target {target.name} is degraded",
                        "monitoring",
                    )
            await asyncio.sleep(10)

    def stop_monitoring(self):
        """stop_monitoring。
        """
        self._running = False

    def get_metric(self, name: str) -> Optional[MetricCollector]:
        """获取 metric。

        Args:
            name: name 参数。
        """
        return self.metrics.get(name)

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取 all_metrics。
        """
        result = {}
        for name, collector in self.metrics.items():
            result[name] = {
                "type": collector.metric_type.value,
                "latest": collector.get_latest(),
                "avg": collector.get_average(),
                "count": len(collector.values),
            }
        return result

    def get_target_status(self) -> Dict[str, Dict[str, Any]]:
        """获取 target_status。
        """
        return {
            name: {
                "status": target.status.value,
                "last_check": target.last_check.isoformat(),
                "last_error": target.last_error,
            }
            for name, target in self.targets.items()
        }


def create_monitoring_system() -> MonitoringSystem:
    """创建 monitoring_system。
    """
    return MonitoringSystem()


monitoring_system = MonitoringSystem.get_instance()