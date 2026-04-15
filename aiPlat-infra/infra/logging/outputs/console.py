from .base import LogOutput


class ConsoleOutput(LogOutput):
    def __init__(self, colorize: bool = True):
        self.colorize = colorize

    def emit(self, record) -> None:
        print(record)

    def close(self) -> None:
        pass
