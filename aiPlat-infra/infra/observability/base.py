"""observability/base：链路追踪与 OTel 抽象接口。"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class Tracer(ABC):
    """链路追踪器抽象接口。"""

    @abstractmethod
    def start_span(self, name: str, context: Optional["SpanContext"] = None) -> "Span":
        """开启 span。

        Args:
            name: span 名。
            context: 可选父上下文。
        """
        pass

    @abstractmethod
    def get_current_span(self) -> Optional["Span"]:
        """获取当前 span。"""
        pass


class Span(ABC):
    """追踪 span 抽象接口。"""

    @abstractmethod
    def set_attribute(self, key: str, value: Any) -> None:
        """设置属性。

        Args:
            key: 属性键。
            value: 属性值。
        """
        pass

    @abstractmethod
    def add_event(self, name: str, attributes: Dict = None) -> None:
        """添加事件。

        Args:
            name: 事件名。
            attributes: 可选属性。
        """
        pass

    @abstractmethod
    def set_status(self, code: str, message: str = "") -> None:
        """设置状态。

        Args:
            code: 状态码。
            message: 可选说明。
        """
        pass

    @abstractmethod
    def end(self) -> None:
        """结束 span。"""
        pass


class SpanContext:
    """Span 上下文。"""

    def __init__(self, trace_id: str = "", span_id: str = "", sampled: bool = True):
        """初始化上下文。

        Args:
            trace_id: 追踪 ID。
            span_id: Span ID。
            sampled: 是否采样。
        """
        self.trace_id = trace_id
        self.span_id = span_id
        self.sampled = sampled


class OTelMetrics(ABC):
    """OpenTelemetry 指标抽象接口。"""

    @abstractmethod
    def counter(self, name: str, **kwargs) -> "Counter":
        """创建计数器。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def up_down_counter(self, name: str, **kwargs) -> "UpDownCounter":
        """创建可增减计数器。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def histogram(self, name: str, **kwargs) -> "Histogram":
        """创建直方图。

        Args:
            name: 指标名。
            kwargs: 附加关键字参数。
        """
        pass


class Counter:
    """OTel 计数器。"""

    def __init__(self, name: str, unit: str = "", description: str = ""):
        """初始化计数器。

        Args:
            name: 指标名。
            unit: 单位。
            description: 描述。
        """
        self.name = name
        self.unit = unit
        self.description = description
        self._value = 0

    def add(self, value: float, attributes: Dict = None) -> None:
        """累加。

        Args:
            value: 增量。
            attributes: 可选属性。
        """
        self._value += value


class UpDownCounter:
    """可增减计数器。"""

    def __init__(self, name: str, unit: str = "", description: str = ""):
        """初始化。

        Args:
            name: 指标名。
            unit: 单位。
            description: 描述。
        """
        self.name = name
        self.unit = unit
        self.description = description
        self._value = 0

    def add(self, value: float, attributes: Dict = None) -> None:
        """增减。

        Args:
            value: 增量（可为负）。
            attributes: 可选属性。
        """
        self._value += value


class Histogram:
    """OTel 直方图。"""

    def __init__(self, name: str, unit: str = "", description: str = ""):
        """初始化直方图。

        Args:
            name: 指标名。
            unit: 单位。
            description: 描述。
        """
        self.name = name
        self.unit = unit
        self.description = description
        self._values: List[float] = []

    def record(self, value: float, attributes: Dict = None) -> None:
        """记录观测。

        Args:
            value: 观测值。
            attributes: 可选属性。
        """
        self._values.append(value)


class OTelLogger(ABC):
    """OTel 日志抽象接口。"""

    @abstractmethod
    def log(self, record: "LogRecord") -> None:
        """写出日志记录。

        Args:
            record: 日志记录。
        """
        pass


class LogRecord:
    """结构化日志记录。"""

    def __init__(self, message: str, severity: str = "INFO", attributes: Dict = None):
        """初始化记录。

        Args:
            message: 消息。
            severity: 严重级别。
            attributes: 可选属性。
        """
        self.message = message
        self.severity = severity
        self.attributes = attributes or {}


class Propagator(ABC):
    """上下文传播抽象接口。"""

    @abstractmethod
    def inject(self, context: SpanContext, carrier: Dict) -> None:
        """注入上下文到载体。

        Args:
            context: Span 上下文。
            carrier: 载体 dict。
        """
        pass

    @abstractmethod
    def extract(self, carrier: Dict) -> SpanContext:
        """从载体提取上下文。

        Args:
            carrier: 载体 dict。
        """
        pass


class SpanExporter(ABC):
    """Span 导出器抽象接口。"""

    @abstractmethod
    def export(self, spans: List[Span]) -> None:
        """导出 spans。

        Args:
            spans: Span 列表。
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """关闭导出器。"""
        pass
