"""file：模块接口。"""

from .base import LogOutput


class FileOutput(LogOutput):
    """FileOutput。"""
    def __init__(self, path: str, max_bytes: int = 10485760, backup_count: int = 10):
        """初始化。

        Args:
            path: 路径。
            max_bytes: max_bytes 参数。
            backup_count: backup_count 参数。
        """
        import logging.handlers
        import os

        self.path = path
        self._handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )

    def emit(self, record) -> None:
        """emit。

        Args:
            record: record 参数。
        """
        self._handler.emit(record)

    def close(self) -> None:
        """close。
        """
        self._handler.close()
