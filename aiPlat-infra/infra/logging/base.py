"""logging/base：日志抽象接口与上下文。"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from .schemas import LogRecord


class Logger(ABC):
    """分级日志抽象接口。"""

    @abstractmethod
    def debug(self, msg: str, **kwargs: Any) -> None:
        """输出 debug 日志。

        Args:
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def info(self, msg: str, **kwargs: Any) -> None:
        """输出 info 日志。

        Args:
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def warning(self, msg: str, **kwargs: Any) -> None:
        """输出 warning 日志。

        Args:
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def error(self, msg: str, **kwargs: Any) -> None:
        """输出 error 日志。

        Args:
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def critical(self, msg: str, **kwargs: Any) -> None:
        """输出 critical 日志。

        Args:
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def log(self, level: str, msg: str, **kwargs: Any) -> None:
        """按级别输出日志。

        Args:
            level: 日志级别。
            msg: 日志消息。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def child(self, name: str) -> "Logger":
        """创建子 logger。

        Args:
            name: 子 logger 名。
        """
        pass


class StructuredLogger(ABC):
    """结构化事件日志抽象接口。"""

    @abstractmethod
    def log_event(self, event: Any) -> None:
        """记录事件。

        Args:
            event: 事件对象。
        """
        pass

    @abstractmethod
    def log_request(self, request: Any) -> None:
        """记录请求。

        Args:
            request: 请求对象。
        """
        pass

    @abstractmethod
    def log_response(self, response: Any) -> None:
        """记录响应。

        Args:
            response: 响应对象。
        """
        pass

    @abstractmethod
    def log_exception(self, exc: Exception, context: Dict[str, Any]) -> None:
        """记录异常。

        Args:
            exc: 异常。
            context: 上下文 dict。
        """
        pass


class Formatter(ABC):
    """日志格式化器抽象接口。"""

    @abstractmethod
    def format(self, record: LogRecord) -> str:
        """格式化日志记录。

        Args:
            record: 日志记录。
        """
        pass

    @abstractmethod
    def format_exception(self, exc: Exception) -> str:
        """格式化异常。

        Args:
            exc: 异常。
        """
        pass


class LogOutput(ABC):
    """日志输出目标抽象接口。"""

    @abstractmethod
    def emit(self, record: LogRecord) -> None:
        """写出一条日志。

        Args:
            record: 日志记录。
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭输出目标。"""
        pass


class LogFilter(ABC):
    """日志过滤器抽象接口。"""

    @abstractmethod
    def filter(self, record: LogRecord) -> bool:
        """是否放行该记录。

        Args:
            record: 日志记录。
        """
        pass


class LogContext:
    """线程/协程局部日志上下文字典。"""

    _context: Dict[str, Any] = {}

    def __init__(self, **kwargs: Any):
        """进入上下文时合并键值。

        Args:
            kwargs: 附加关键字参数。
        """
        self._saved = {}
        for k, v in kwargs.items():
            self._saved[k] = LogContext._context.get(k)
            LogContext._context[k] = v

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for k, v in self._saved.items():
            if v is None:
                del LogContext._context[k]
            else:
                LogContext._context[k] = v

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """读取上下文键。

        Args:
            key: 缓存键。
            default: 默认值。
        """
        return cls._context.get(key, default)

    @classmethod
    def clear(cls) -> None:
        """清空上下文。"""
        cls._context.clear()
