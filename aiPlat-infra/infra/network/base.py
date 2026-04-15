from abc import ABC, abstractmethod
from typing import List, Optional
from .schemas import Service, Endpoint, LoadBalancer, NetworkPolicy, DnsRecord


class NetworkManager(ABC):
    @abstractmethod
    def register_service(self, service: Service) -> str:
        pass

    @abstractmethod
    def deregister_service(self, service_id: str) -> bool:
        pass

    @abstractmethod
    def discover_services(self, name: str) -> List[Endpoint]:
        pass

    @abstractmethod
    def get_load_balancer(self, name: str) -> Optional[LoadBalancer]:
        pass

    @abstractmethod
    def apply_policy(self, policy: NetworkPolicy) -> bool:
        pass

    @abstractmethod
    def get_dns_records(self, domain: str) -> List[DnsRecord]:
        pass
