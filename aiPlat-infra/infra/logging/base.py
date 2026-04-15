from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from .schemas import LogRecord


class Logger(ABC):
    @abstractmethod
    def debug(self, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def info(self, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def warning(self, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def error(self, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def critical(self, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def log(self, level: str, msg: str, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def child(self, name: str) -> "Logger":
        pass


class StructuredLogger(ABC):
    @abstractmethod
    def log_event(self, event: Any) -> None:
        pass

    @abstractmethod
    def log_request(self, request: Any) -> None:
        pass

    @abstractmethod
    def log_response(self, response: Any) -> None:
        pass

    @abstractmethod
    def log_exception(self, exc: Exception, context: Dict[str, Any]) -> None:
        pass


class Formatter(ABC):
    @abstractmethod
    def format(self, record: LogRecord) -> str:
        pass

    @abstractmethod
    def format_exception(self, exc: Exception) -> str:
        pass


class LogOutput(ABC):
    @abstractmethod
    def emit(self, record: LogRecord) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class LogFilter(ABC):
    @abstractmethod
    def filter(self, record: LogRecord) -> bool:
        pass


class LogContext:
    _context: Dict[str, Any] = {}

    def __init__(self, **kwargs: Any):
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
        return cls._context.get(key, default)

    @classmethod
    def clear(cls) -> None:
        cls._context.clear()
