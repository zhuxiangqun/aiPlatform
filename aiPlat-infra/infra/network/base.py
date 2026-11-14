"""network/base：网络与服务发现抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, Optional
from .schemas import Service, Endpoint, LoadBalancer, NetworkPolicy, DnsRecord


class NetworkManager(ABC):
    """网络管理器抽象接口。"""

    @abstractmethod
    def register_service(self, service: Service) -> str:
        """注册服务。

        Args:
            service: 服务对象。
        """
        pass

    @abstractmethod
    def deregister_service(self, service_id: str) -> bool:
        """注销服务。

        Args:
            service_id: 服务 ID。
        """
        pass

    @abstractmethod
    def discover_services(self, name: str) -> List[Endpoint]:
        """按名称发现服务端点。

        Args:
            name: 服务名。
        """
        pass

    @abstractmethod
    def get_load_balancer(self, name: str) -> Optional[LoadBalancer]:
        """获取负载均衡器。

        Args:
            name: 名称。
        """
        pass

    @abstractmethod
    def apply_policy(self, policy: NetworkPolicy) -> bool:
        """应用网络策略。

        Args:
            policy: 网络策略。
        """
        pass

    @abstractmethod
    def get_dns_records(self, domain: str) -> List[DnsRecord]:
        """获取 DNS 记录。

        Args:
            domain: 域名。
        """
        pass
