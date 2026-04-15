from .base import LogOutput


class FileOutput(LogOutput):
    def __init__(self, path: str, max_bytes: int = 10485760, backup_count: int = 10):
        import logging.handlers
        import os

        self.path = path
        self._handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )

    def emit(self, record) -> None:
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()
