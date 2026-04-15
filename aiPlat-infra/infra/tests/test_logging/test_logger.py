"""logging 模块测试"""

import pytest


class TestLogger:
    """日志器测试"""

    def test_logger_factory(self):
        """测试日志器工厂"""
        from infra.logging.factory import create_logger

        logger = create_logger("test")
        assert logger is not None

    def test_simple_logger(self):
        """测试简单日志器"""
        from infra.logging.factory import SimpleLogger

        logger = SimpleLogger("test")
        assert logger is not None
