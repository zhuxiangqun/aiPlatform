"""sensitive_data：模块接口。"""

from ..base import LogFilter
from ..schemas import LogRecord


class SensitiveDataFilter(LogFilter):
    """SensitiveDataFilter。"""
    SENSITIVE_FIELDS = {"password", "token", "secret", "api_key"}

    def filter(self, record: LogRecord) -> bool:
        """filter。

        Args:
            record: record 参数。
        """
        for field in self.SENSITIVE_FIELDS:
            if field in record.extra:
                record.extra[field] = "***REDACTED***"
        return True
