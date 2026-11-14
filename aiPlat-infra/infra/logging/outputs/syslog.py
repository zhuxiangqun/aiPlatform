"""syslog：模块接口。"""

from .base import LogOutput


class SyslogOutput(LogOutput):
    """SyslogOutput。"""
    def __init__(self, host: str = "localhost", port: int = 514):
        """初始化。

        Args:
            host: host 参数。
            port: port 参数。
        """
        import logging.handlers

        self._handler = logging.handlers.SysLogHandler(address=(host, port))

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
