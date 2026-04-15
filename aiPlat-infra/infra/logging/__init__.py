from .base import Logger, StructuredLogger, Formatter, LogOutput, LogFilter, LogContext
from .schemas import LoggingConfig, LogEvent, LogRecord, FileConfig, StructuredConfig
from .factory import create_logger

__all__ = [
    "Logger",
    "StructuredLogger",
    "Formatter",
    "LogOutput",
    "LogFilter",
    "LogContext",
    "LoggingConfig",
    "LogEvent",
    "LogRecord",
    "FileConfig",
    "StructuredConfig",
    "create_logger",
]

try:
    from .formatters import JSONFormatter, TextFormatter, ConsoleFormatter

    __all__.extend(["JSONFormatter", "TextFormatter", "ConsoleFormatter"])
except ImportError:
    pass

try:
    from .outputs import ConsoleOutput, FileOutput, SyslogOutput

    __all__.extend(["ConsoleOutput", "FileOutput", "SyslogOutput"])
except ImportError:
    pass

try:
    from .filters import SensitiveDataFilter

    __all__.append("SensitiveDataFilter")
except ImportError:
    pass
