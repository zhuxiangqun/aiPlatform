"""factory：模块接口。"""

from typing import Optional, List, Any
from .base import Logger, StructuredLogger
from .schemas import LoggingConfig
from .formatters import JSONFormatter, TextFormatter, ConsoleFormatter


class SimpleLogger(Logger):
    """SimpleLogger。"""
    def __init__(self, name: str, config: Optional[LoggingConfig] = None):
        """初始化。

        Args:
            name: name 参数。
            config: config 参数。
        """
        self.name = name
        self.config = config or LoggingConfig()
        self._formatters = {
            "json": JSONFormatter(),
            "text": TextFormatter(),
            "console": ConsoleFormatter(),
        }

    def _get_formatter(self):
        return self._formatters.get(self.config.format, JSONFormatter())

    def _log(self, level: str, msg: str, **kwargs: Any) -> None:
        from datetime import datetime, timezone
        from .schemas import LogRecord
        from .base import LogContext

        record = LogRecord(
            level=level,
            message=msg,
            timestamp=datetime.now(timezone.utc),
            logger_name=self.name,
            trace_id=LogContext.get("trace_id"),
            request_id=LogContext.get("request_id"),
            user_id=LogContext.get("user_id"),
            extra=kwargs,
        )

        formatter = self._get_formatter()
        output = formatter.format(record)

        if "console" in self.config.output:
            print(output)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """debug。

        Args:
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log("DEBUG", msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """info。

        Args:
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log("INFO", msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """warning。

        Args:
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log("WARNING", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """error。

        Args:
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log("ERROR", msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        """critical。

        Args:
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log("CRITICAL", msg, **kwargs)

    def log(self, level: str, msg: str, **kwargs: Any) -> None:
        """log。

        Args:
            level: level 参数。
            msg: msg 参数。
            kwargs: kwargs 参数。
        """
        self._log(level.upper(), msg, **kwargs)

    def child(self, name: str) -> "Logger":
        """child。

        Args:
            name: name 参数。
        """
        return SimpleLogger(f"{self.name}.{name}", self.config)


def create_logger(name: str, config: Optional[LoggingConfig] = None) -> Logger:
    """创建 logger。

    Args:
        name: name 参数。
        config: config 参数。
    """
    return SimpleLogger(name, config)
