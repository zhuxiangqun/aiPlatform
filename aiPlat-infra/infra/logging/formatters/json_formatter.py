from datetime import datetime
import json
from ..base import Formatter
from ..schemas import LogRecord


class JSONFormatter(Formatter):
    def __init__(self, include_extra: bool = True):
        self.include_extra = include_extra

    def format(self, record: LogRecord) -> str:
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
        import traceback

        return json.dumps(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
