from ..base import LogFilter
from ..schemas import LogRecord


class SensitiveDataFilter(LogFilter):
    SENSITIVE_FIELDS = {"password", "token", "secret", "api_key"}

    def filter(self, record: LogRecord) -> bool:
        for field in self.SENSITIVE_FIELDS:
            if field in record.extra:
                record.extra[field] = "***REDACTED***"
        return True
