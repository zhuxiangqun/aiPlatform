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
        pass

    @abstractmethod
    def close(self) -> None:
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
        pass

    @abstractmethod
    def register_instance(self, service: Type, instance: Any) -> None:
        pass

    @abstractmethod
    def register_factory(self, service: Type, factory: Callable[..., Any]) -> None:
        pass

    @abstractmethod
    def resolve(self, service: Type) -> Any:
        pass

    @abstractmethod
    def resolve_all(self, service: Type) -> List[Any]:
        pass

    @abstractmethod
    def create_scope(self, scope_name: str) -> IScope:
        pass

    @contextmanager
    @abstractmethod
    def scope(self, scope_name: str):
        pass

    @abstractmethod
    def clear(self) -> None:
        pass
