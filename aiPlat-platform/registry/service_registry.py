"""
Service Registry - 服务注册中心
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum
from threading import Lock


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceInstance(BaseModel):
    """服务实例"""
    instance_id: str
    service_name: str
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.HEALTHY
    metadata: Dict[str, Any] = {}
    version: str = "1.0.0"
    registered_at: datetime = datetime.now()
    last_heartbeat: datetime = datetime.now()


class ServiceRegistry:
    """服务注册中心"""

    def __init__(self):
        self._services: Dict[str, Dict[str, ServiceInstance]] = {}
        self._lock = Lock()

    def register(
        self,
        service_name: str,
        instance_id: str,
        host: str,
        port: int,
        metadata: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
    ) -> ServiceInstance:
        """注册服务实例"""
        with self._lock:
            if service_name not in self._services:
                self._services[service_name] = {}

            instance = ServiceInstance(
                instance_id=instance_id,
                service_name=service_name,
                host=host,
                port=port,
                metadata=metadata or {},
                version=version,
            )
            self._services[service_name][instance_id] = instance
            return instance

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """注销服务实例"""
        with self._lock:
            if service_name in self._services and instance_id in self._services[service_name]:
                del self._services[service_name][instance_id]
                return True
        return False

    def discover(self, service_name: str, version: Optional[str] = None) -> list[ServiceInstance]:
        """发现服务实例"""
        with self._lock:
            instances = list(self._services.get(service_name, {}).values())

            if version:
                instances = [i for i in instances if i.version == version]

            instances = [i for i in instances if i.status == ServiceStatus.HEALTHY]
            return instances

    def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """心跳"""
        with self._lock:
            if service_name in self._services and instance_id in self._services[service_name]:
                instance = self._services[service_name][instance_id]
                instance.last_heartbeat = datetime.now()
                instance.status = ServiceStatus.HEALTHY
                return True
        return False

    def set_unhealthy(self, service_name: str, instance_id: str) -> bool:
        """标记不健康"""
        with self._lock:
            if service_name in self._services and instance_id in self._services[service_name]:
                self._services[service_name][instance_id].status = ServiceStatus.UNHEALTHY
                return True
        return False

    def get_instances_count(self, service_name: str) -> int:
        """获取实例数量"""
        with self._lock:
            return len(self._services.get(service_name, {}))

    def list_services(self) -> list[str]:
        """列出所有服��"""
        with self._lock:
            return list(self._services.keys())


service_registry = ServiceRegistry()