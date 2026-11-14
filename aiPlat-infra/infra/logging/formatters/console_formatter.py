"""console_formatter：模块接口。"""

from ..base import Formatter
from ..schemas import LogRecord


class ConsoleFormatter(Formatter):
    """ConsoleFormatter。"""
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: LogRecord) -> str:
        """format。

        Args:
            record: record 参数。
        """
        color = self.LEVEL_COLORS.get(record.level.upper(), "")
        reset = self.RESET if color else ""
        return f"{color}[{record.timestamp}] [{record.level.upper()}] {record.message}{reset}"

    def format_exception(self, exc: Exception) -> str:
        """format_exception。

        Args:
            exc: exc 参数。
        """
        import traceback

        return f"{self.LEVEL_COLORS['ERROR']}{type(exc).__name__}: {exc}{self.RESET}\n{traceback.format_exc()}"
