"""console：模块接口。"""

from .base import LogOutput


class ConsoleOutput(LogOutput):
    """ConsoleOutput。"""
    def __init__(self, colorize: bool = True):
        """初始化。

        Args:
            colorize: colorize 参数。
        """
        self.colorize = colorize

    def emit(self, record) -> None:
        """emit。

        Args:
            record: record 参数。
        """
        print(record)

    def close(self) -> None:
        """close。
        """
        pass
