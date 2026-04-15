from ..base import Formatter
from ..schemas import LogRecord


class ConsoleFormatter(Formatter):
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.level.upper(), "")
        reset = self.RESET if color else ""
        return f"{color}[{record.timestamp}] [{record.level.upper()}] {record.message}{reset}"

    def format_exception(self, exc: Exception) -> str:
        import traceback

        return f"{self.LEVEL_COLORS['ERROR']}{type(exc).__name__}: {exc}{self.RESET}\n{traceback.format_exc()}"
