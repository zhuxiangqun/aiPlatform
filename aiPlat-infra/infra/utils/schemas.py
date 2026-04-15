"""
Utils Schemas - 工具模块数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorCategory(Enum):
    """错误分类"""

    VALIDATION = "validation"
    NETWORK = "network"
    DATABASE = "database"
    LLM_API = "llm_api"
    PARSING = "parsing"
    SYSTEM = "system"
    BUSINESS = "business"


class ErrorLevel(Enum):
    """错误级别"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ErrorEvent:
    """错误事件"""

    error_id: str
    category: ErrorCategory
    level: ErrorLevel
    message: str
    exception: Optional[Exception]
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    trace_id: Optional[str] = None


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    errors: List["ValidationError"] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ValidationError:
    """验证错误"""

    field: str
    message: str
    code: str


@dataclass
class Rule:
    """验证规则"""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleConfig:
    """规则配置"""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)
