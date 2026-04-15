from .base import LogOutput


class SyslogOutput(LogOutput):
    def __init__(self, host: str = "localhost", port: int = 514):
        import logging.handlers

        self._handler = logging.handlers.SysLogHandler(address=(host, port))

    def emit(self, record) -> None:
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()
