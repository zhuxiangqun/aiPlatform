"""
Utils Module - 工具函数

提供通用工具函数、错误处理、验证器、加密等能力

文档位置：docs/utils/index.md

文件结构：
├── __init__.py              # 模块导出
├── base.py                  # 基础接口
├── factory.py               # 工厂函数
├── schemas.py               # 数据模型
├── error_handler.py         # 错误处理
├── validator.py            # 输入验证
├── security.py             # 安全工具
├── async_utils.py          # 异步工具
└── helpers.py              # 通用辅助

子模块说明：
- errors: 错误处理 (ErrorHandler, ErrorEvent)
- validation: 输入验证 (InputValidator)
- security: 安全工具 (哈希、加密、令牌)
- async_utils: 异步工具 (重试、超时)
"""

from .error_handler import (
    ErrorHandler,
    ErrorEvent,
    ErrorCategory,
    ErrorLevel,
)
from .validator import (
    InputValidator,
    ValidationResult,
    Rule,
)
from .security import SecurityUtils
from .async_utils import async_retry, async_timeout
from .factory import get_error_handler, get_validator, get_security_utils

__all__ = [
    "ErrorHandler",
    "ErrorEvent",
    "ErrorCategory",
    "ErrorLevel",
    "InputValidator",
    "ValidationResult",
    "Rule",
    "SecurityUtils",
    "async_retry",
    "async_timeout",
    "get_error_handler",
    "get_validator",
    "get_security_utils",
]
