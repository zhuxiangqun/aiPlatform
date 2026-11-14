"""
DIContainer Interface - 依赖注入容器接口定义

文档位置：docs/di/index.md
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Type

from .schemas import Lifetime, ServiceDescriptor


class IScope(ABC):
    """作用域接口"""

    @abstractmethod
    def resolve(self, service: Type) -> Any:
        """resolve。

        Args:
            service: service 参数。
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """close。
        """
        pass


class DIContainer(ABC):
    """依赖注入容器接口"""

    @abstractmethod
    def register(
        self,
        service: Type,
        implementation: Type,
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None:
        """register。

        Args:
            service: service 参数。
            implementation: implementation 参数。
            lifetime: lifetime 参数。
        """
        pass

    @abstractmethod
    def register_instance(self, service: Type, instance: Any) -> None:
        """register_instance。

        Args:
            service: service 参数。
            instance: instance 参数。
        """
        pass

    @abstractmethod
    def register_factory(self, service: Type, factory: Callable[..., Any]) -> None:
        """register_factory。

        Args:
            service: service 参数。
            factory: factory 参数。
        """
        pass

    @abstractmethod
    def resolve(self, service: Type) -> Any:
        """resolve。

        Args:
            service: service 参数。
        """
        pass

    @abstractmethod
    def resolve_all(self, service: Type) -> List[Any]:
        """resolve_all。

        Args:
            service: service 参数。
        """
        pass

    @abstractmethod
    def create_scope(self, scope_name: str) -> IScope:
        """创建 scope。

        Args:
            scope_name: scope_name 参数。
        """
        pass

    @contextmanager
    @abstractmethod
    def scope(self, scope_name: str):
        """scope。

        Args:
            scope_name: scope_name 参数。
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """clear。
        """
        pass
