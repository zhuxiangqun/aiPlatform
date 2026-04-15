"""
DI Registries - 服务注册表

文档位置：docs/di/index.md
"""

from typing import Any, Dict, Type

from .schemas import ServiceDescriptor, Lifetime


class ServiceRegistry:
    """
    服务注册表

    管理所有已注册的服务
    """

    def __init__(self):
        self._services: Dict[Type, ServiceDescriptor] = {}

    def register(self, descriptor: ServiceDescriptor) -> None:
        """注册服务"""
        self._services[descriptor.service] = descriptor

    def unregister(self, service: Type) -> bool:
        """注销服务"""
        if service in self._services:
            del self._services[service]
            return True
        return False

    def get(self, service: Type) -> ServiceDescriptor:
        """获取服务描述符"""
        return self._services.get(service)

    def has(self, service: Type) -> bool:
        """检查服务是否已注册"""
        return service in self._services

    def list_services(self) -> Dict[Type, ServiceDescriptor]:
        """列出所有服务"""
        return self._services.copy()

    def list_by_lifetime(self, lifetime: Lifetime) -> Dict[Type, ServiceDescriptor]:
        """按生命周期过滤"""
        return {s: d for s, d in self._services.items() if d.lifetime == lifetime}
