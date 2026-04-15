"""
Utils Factory - 工具模块工厂函数
"""

from typing import Optional

from .error_handler import ErrorHandler, ErrorHandlerImpl
from .validator import InputValidator, InputValidatorImpl
from .security import SecurityUtils


_error_handler_instance: Optional[ErrorHandler] = None
_validator_instance: Optional[InputValidator] = None
_security_utils_instance: Optional[SecurityUtils] = None


def get_error_handler() -> ErrorHandler:
    """获取错误处理器单例"""
    global _error_handler_instance
    if _error_handler_instance is None:
        _error_handler_instance = ErrorHandlerImpl()
    return _error_handler_instance


def get_validator() -> InputValidator:
    """获取验证器单例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = InputValidatorImpl()
    return _validator_instance


def get_security_utils() -> SecurityUtils:
    """获取安全工具单例"""
    global _security_utils_instance
    if _security_utils_instance is None:
        _security_utils_instance = SecurityUtils()
    return _security_utils_instance
