"""monitoring/base：指标、健康检查与告警抽象。"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class MetricsCollector(ABC):
    """指标采集器抽象接口。"""

    @abstractmethod
    def counter(self, name: str, **kwargs) -> "Counter":
        """创建或获取计数器。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def gauge(self, name: str, **kwargs) -> "Gauge":
        """创建或获取仪表盘指标。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def histogram(self, name: str, **kwargs) -> "Histogram":
        """创建或获取直方图。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def record(self, name: str, value: float, labels: Dict = None) -> None:
        """记录一次观测值。

        Args:
            name: 指标名。
            value: 观测值。
            labels: 可选标签。
        """
        pass

    @abstractmethod
    def get_metrics(self) -> List["Metric"]:
        """导出当前指标快照。"""
        pass

    @abstractmethod
    def export(self) -> str:
        """导出序列化指标文本。"""
        pass


class Counter:
    """简单计数器。"""

    def __init__(self, name: str, labels: Dict = None):
        """初始化计数器。

        Args:
            name: 指标名。
            labels: 可选标签。
        """
        self.name = name
        self.labels = labels or {}
        self._value = 0

    def inc(self, value: float = 1) -> None:
        """增加计数。

        Args:
            value: 增量，默认 1。
        """
        self._value += value


class Gauge:
    """仪表盘指标。"""

    def __init__(self, name: str, labels: Dict = None):
        """初始化仪表盘。

        Args:
            name: 指标名。
            labels: 可选标签。
        """
        self.name = name
        self.labels = labels or {}
        self._value = 0.0

    def set(self, value: float) -> None:
        """设置当前值。

        Args:
            value: 新值。
        """
        self._value = value


class Histogram:
    """直方图观测。"""

    def __init__(self, name: str, labels: Dict = None):
        """初始化直方图。

        Args:
            name: 指标名。
            labels: 可选标签。
        """
        self.name = name
        self.labels = labels or {}
        self._values: List[float] = []

    def observe(self, value: float) -> None:
        """记录观测。

        Args:
            value: 观测值。
        """
        self._values.append(value)


class Metric:
    """单条指标快照。"""

    def __init__(self, name: str, value: float, labels: Dict = None):
        """初始化指标。

        Args:
            name: 指标名。
            value: 当前值。
            labels: 可选标签。
        """
        self.name = name
        self.value = value
        self.labels = labels or {}


class HealthChecker(ABC):
    """健康检查抽象接口。"""

    @abstractmethod
    def check(self) -> "HealthStatus":
        """执行健康检查。"""
        pass

    @abstractmethod
    def register_check(self, name: str, check_fn) -> None:
        """注册检查项。

        Args:
            name: 检查名。
            check_fn: 检查可调用对象。
        """
        pass


class HealthStatus:
    """健康检查结果。"""

    def __init__(self, healthy: bool, message: str = "", details: Dict = None):
        """初始化结果。

        Args:
            healthy: 是否健康。
            message: 说明文本。
            details: 可选详情。
        """
        self.healthy = healthy
        self.message = message
        self.details = details or {}


class AlertManager(ABC):
    """告警管理抽象接口。"""

    @abstractmethod
    def trigger(self, alert: "Alert") -> None:
        """触发告警。

        Args:
            alert: 告警对象。
        """
        pass

    @abstractmethod
    def get_active_alerts(self) -> List["Alert"]:
        """获取活跃告警列表。"""
        pass

    @abstractmethod
    def silence(self, alert_id: str, duration: int) -> bool:
        """静默告警。

        Args:
            alert_id: 告警 ID。
            duration: 静默秒数。
        """
        pass


class Alert:
    """告警实体。"""

    def __init__(self, name: str, level: str, message: str, details: Dict = None):
        """初始化告警。

        Args:
            name: 告警名。
            level: 级别。
            message: 消息。
            details: 可选详情。
        """
        self.id = f"alert-{name}"
        self.name = name
        self.level = level
        self.message = message
        self.details = details or {}
        self.timestamp = None
