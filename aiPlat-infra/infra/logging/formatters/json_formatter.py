"""json_formatter：模块接口。"""

from datetime import datetime
import json
from ..base import Formatter
from ..schemas import LogRecord


class JSONFormatter(Formatter):
    """JSONFormatter。"""
    def __init__(self, include_extra: bool = True):
        """初始化。

        Args:
            include_extra: include_extra 参数。
        """
        self.include_extra = include_extra

    def format(self, record: LogRecord) -> str:
        """format。

        Args:
            record: record 参数。
        """
        data = {
            "timestamp": record.timestamp.isoformat()
            if isinstance(record.timestamp, datetime)
            else str(record.timestamp),
            "level": record.level,
            "message": record.message,
            "logger": record.logger_name,
        }

        if record.trace_id:
            data["trace_id"] = record.trace_id
        if record.request_id:
            data["request_id"] = record.request_id
        if record.user_id:
            data["user_id"] = record.user_id

        if self.include_extra and record.extra:
            data["extra"] = record.extra

        return json.dumps(data, ensure_ascii=False)

    def format_exception(self, exc: Exception) -> str:
        """format_exception。

        Args:
            exc: exc 参数。
        """
        import traceback

        return json.dumps(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
