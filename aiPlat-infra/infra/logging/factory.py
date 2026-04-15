from typing import Optional, List, Any
from .base import Logger, StructuredLogger
from .schemas import LoggingConfig
from .formatters import JSONFormatter, TextFormatter, ConsoleFormatter


class SimpleLogger(Logger):
    def __init__(self, name: str, config: Optional[LoggingConfig] = None):
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
        from datetime import datetime
        from .schemas import LogRecord
        from .base import LogContext

        record = LogRecord(
            level=level,
            message=msg,
            timestamp=datetime.now(),
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
        self._log("DEBUG", msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log("INFO", msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log("WARNING", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log("ERROR", msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log("CRITICAL", msg, **kwargs)

    def log(self, level: str, msg: str, **kwargs: Any) -> None:
        self._log(level.upper(), msg, **kwargs)

    def child(self, name: str) -> "Logger":
        return SimpleLogger(f"{self.name}.{name}", self.config)


def create_logger(name: str, config: Optional[LoggingConfig] = None) -> Logger:
    return SimpleLogger(name, config)
