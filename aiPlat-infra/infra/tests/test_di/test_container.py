"""DI 模块测试"""

import pytest
from dataclasses import dataclass, field

from infra.di.container import DIContainerImpl
from infra.di.schemas import Lifetime


@dataclass
class TestService:
    value: str = field(default="test")


class TestContainer:
    """依赖注入容器测试"""

    def test_register_singleton(self):
        """测试注册单例"""
        container = DIContainerImpl()
        container.register(TestService, TestService, lifetime=Lifetime.SINGLETON)
        instance = container.resolve(TestService)
        assert instance is not None

    def test_register_transient(self):
        """测试注册瞬态"""
        container = DIContainerImpl()
        container.register(TestService, TestService, lifetime=Lifetime.TRANSIENT)
        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)
        assert instance1 is not instance2

    def test_register_instance(self):
        """测试注册实例"""
        container = DIContainerImpl()
        instance = TestService(value="custom")
        container.register_instance(TestService, instance)
        resolved = container.resolve(TestService)
        assert resolved.value == "custom"

    def test_register_factory(self):
        """测试注册工厂"""
        container = DIContainerImpl()

        def create_service() -> str:
            return "created"

        container.register_factory(str, create_service)
        result = container.resolve(str)
        assert result == "created"

    def test_scope(self):
        """测试作用域"""
        container = DIContainerImpl()
        container.register(TestService, TestService, lifetime=Lifetime.SCOPED)
        with container.scope("request") as scope:
            instance = scope.resolve(TestService)
            assert instance is not None
