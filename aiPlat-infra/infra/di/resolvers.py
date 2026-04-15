"""
DI Resolvers - 依赖解析器

文档位置：docs/di/index.md
"""

from typing import Any, Callable, Dict, Type


class Resolver:
    """
    依赖解析器

    负责解析依赖关系
    """

    def __init__(self, container: Any):
        self._container = container

    def resolve(self, service: Type) -> Any:
        """解析服务"""
        return self._container.resolve(service)

    def can_resolve(self, service: Type) -> bool:
        """检查是否可以解析"""
        return service in self._container._services


class ChainResolver:
    """链式解析器"""

    def __init__(self):
        self._resolvers = []

    def add_resolver(self, resolver: Resolver) -> None:
        self._resolvers.append(resolver)

    def resolve(self, service: Type) -> Any:
        """按顺序尝试解析"""
        for resolver in self._resolvers:
            if resolver.can_resolve(service):
                return resolver.resolve(service)
        raise ValueError(f"Cannot resolve {service}")
