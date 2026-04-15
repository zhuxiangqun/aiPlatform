"""utils 模块测试"""

import pytest

from infra.utils.validator import EmailRule, RequiredRule
from infra.utils.helpers import (
    now_utc,
    format_timestamp,
    parse_timestamp,
    safe_json_loads,
    safe_json_dumps,
)


class TestValidator:
    """验证器测试"""

    def test_email_rule(self):
        """测试邮箱规则"""
        rule = EmailRule()
        assert rule.validate("test@example.com") is True
        assert rule.validate("invalid") is False

    def test_required_rule(self):
        """测试必填规则"""
        rule = RequiredRule()
        assert rule.validate("value") is True
        assert rule.validate("") is False
        assert rule.validate(None) is False


class TestHelpers:
    """辅助工具测试"""

    def test_now_utc(self):
        """测试获取当前时间"""
        result = now_utc()
        assert result is not None

    def test_safe_json_loads(self):
        """测试安全JSON解析"""
        result = safe_json_loads('{"key": "value"}')
        assert result is not None

    def test_safe_json_dumps(self):
        """测试安全JSON序列化"""
        result = safe_json_dumps({"key": "value"})
        assert "key" in result


class TestSecurity:
    """安全工具测试"""

    def test_security_utils(self):
        """测试安全工具类"""
        from infra.utils.security import SecurityUtils

        utils = SecurityUtils()
        assert utils is not None
