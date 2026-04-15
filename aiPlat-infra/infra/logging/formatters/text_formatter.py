from ..base import Formatter
from ..schemas import LogRecord


class TextFormatter(Formatter):
    def __init__(self, template: str = "[{timestamp}] [{level}] {message}"):
        self.template = template

    def format(self, record: LogRecord) -> str:
        return self.template.format(
            timestamp=record.timestamp,
            level=record.level.upper(),
            message=record.message,
            logger=record.logger_name,
        )

    def format_exception(self, exc: Exception) -> str:
        import traceback

        return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
