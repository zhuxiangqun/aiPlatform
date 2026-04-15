"""
Input Validator - 输入验证实现

文档位置：docs/utils/index.md
"""

import re
from typing import Any, List, Optional

from .base import InputValidator
from .schemas import Rule, ValidationError, ValidationResult


class Rule:
    """验证规则基类"""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def validate(self, value: Any) -> bool:
        raise NotImplementedError

    def message(self, field: str) -> str:
        return f"{field} is invalid"


class RequiredRule(Rule):
    """必填规则"""

    def validate(self, value: Any) -> bool:
        return value is not None and value != ""

    def message(self, field: str) -> str:
        return f"{field} is required"


class EmailRule(Rule):
    """邮箱规则"""

    PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    def validate(self, value: Any) -> bool:
        if value is None:
            return False
        return bool(re.match(self.PATTERN, str(value)))

    def message(self, field: str) -> str:
        return f"{field} must be a valid email"


class LengthRule(Rule):
    """长度规则"""

    def __init__(self, min_length: int = 0, max_length: Optional[int] = None):
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, value: Any) -> bool:
        if value is None:
            return False
        length = len(str(value))
        if length < self.min_length:
            return False
        if self.max_length and length > self.max_length:
            return False
        return True

    def message(self, field: str) -> str:
        if self.max_length:
            return f"{field} length must be {self.min_length}-{self.max_length}"
        return f"{field} length must be at least {self.min_length}"


class RegexRule(Rule):
    """正则规则"""

    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)

    def validate(self, value: Any) -> bool:
        if value is None:
            return False
        return bool(self.pattern.match(str(value)))

    def message(self, field: str) -> str:
        return f"{field} format is invalid"


class InputValidatorImpl(InputValidator):
    """输入验证器实现"""

    def __init__(self):
        self._custom_rules: List[Rule] = []

    def validate(self, value: Any, rules: List[Rule]) -> ValidationResult:
        """验证输入"""
        errors = []

        for rule in rules:
            if not rule.validate(value):
                errors.append(
                    ValidationError(
                        field="value", message=rule.message("value"), code=rule.name
                    )
                )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def validate_schema(self, data: dict, schema: dict) -> ValidationResult:
        """验证数据模式"""
        errors = []

        for field, rules in schema.items():
            value = data.get(field)

            for rule in rules:
                if not rule.validate(value):
                    errors.append(
                        ValidationError(
                            field=field, message=rule.message(field), code=rule.name
                        )
                    )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
