"""text_formatter：模块接口。"""

from ..base import Formatter
from ..schemas import LogRecord


class TextFormatter(Formatter):
    """TextFormatter。"""
    def __init__(self, template: str = "[{timestamp}] [{level}] {message}"):
        """初始化。

        Args:
            template: template 参数。
        """
        self.template = template

    def format(self, record: LogRecord) -> str:
        """format。

        Args:
            record: record 参数。
        """
        return self.template.format(
            timestamp=record.timestamp,
            level=record.level.upper(),
            message=record.message,
            logger=record.logger_name,
        )

    def format_exception(self, exc: Exception) -> str:
        """format_exception。

        Args:
            exc: exc 参数。
        """
        import traceback

        return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
