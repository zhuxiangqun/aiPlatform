"""
Utils Base - 工具模块基础接口

文档位置：docs/utils/index.md
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from .schemas import ErrorEvent, ValidationResult


class ErrorHandler(ABC):
    """错误处理器接口"""

    @abstractmethod
    def handle(self, error: Exception, context: dict) -> ErrorEvent:
        """处理错误"""
        pass

    @abstractmethod
    def get_errors(self, filters: dict) -> List[ErrorEvent]:
        """获取错误列表"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """清除错误记录"""
        pass


class InputValidator(ABC):
    """输入验证器接口"""

    @abstractmethod
    def validate(self, value: Any, rules: List) -> ValidationResult:
        """验证输入"""
        pass

    @abstractmethod
    def validate_schema(self, data: dict, schema: dict) -> ValidationResult:
        """验证数据模式"""
        pass
