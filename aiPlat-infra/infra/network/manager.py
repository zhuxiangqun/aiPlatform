import uuid
from typing import List, Optional, Dict
from .base import NetworkManager
from .schemas import (
    Service,
    Endpoint,
    LoadBalancer,
    NetworkPolicy,
    DnsRecord,
    NetworkConfig,
)


class StaticNetworkManager(NetworkManager):
    def __init__(self, config: NetworkConfig):
        self.config = config
        self._services: Dict[str, Service] = {}
        self._dns_records: Dict[str, List[DnsRecord]] = {}
        self._lb_algorithms = {
            "round_robin": self._round_robin,
            "weighted": self._weighted,
            "least_conn": self._least_conn,
        }
        self._lb_index: Dict[str, int] = {}

    def _round_robin(self, backends: List[Endpoint]) -> Optional[Endpoint]:
        if not backends:
            return None
        name = id(backends)
        index = self._lb_index.get(name, 0)
        self._lb_index[name] = (index + 1) % len(backends)
        return backends[index]

    def _weighted(self, backends: List[Endpoint]) -> Optional[Endpoint]:
        weighted = [b for b in backends if b.weight > 0]
        if not weighted:
            return None
        total = sum(b.weight for b in weighted)
        import random

        r = random.randint(1, total)
        cumulative = 0
        for b in weighted:
            cumulative += b.weight
            if cumulative >= r:
                return b
        return weighted[-1]

    def _least_conn(self, backends: List[Endpoint]) -> Optional[Endpoint]:
        healthy = [b for b in backends if b.health]
        if not healthy:
            return None
        return min(healthy, key=lambda b: b.weight)

    def register_service(self, service: Service) -> str:
        service_id = str(uuid.uuid4())
        self._services[service_id] = service
        return service_id

    def deregister_service(self, service_id: str) -> bool:
        if service_id in self._services:
            del self._services[service_id]
            return True
        return False

    def discover_services(self, name: str) -> List[Endpoint]:
        for service in self._services.values():
            if service.name == name:
                return service.endpoints
        return []

    def get_load_balancer(self, name: str) -> Optional[LoadBalancer]:
        endpoints = self.discover_services(name)
        if not endpoints:
            return None
        return LoadBalancer(
            algorithm=self.config.lb_algorithm,
            backends=endpoints,
        )

    def apply_policy(self, policy: NetworkPolicy) -> bool:
        return True

    def get_dns_records(self, domain: str) -> List[DnsRecord]:
        return self._dns_records.get(domain, [])


class ConsulNetworkManager(NetworkManager):
    def __init__(self, config: NetworkConfig):
        self.config = config
        self._client = None
        self._services: Dict[str, Service] = {}

    def _get_client(self):
        if self._client is None:
            import requests

            self._client = requests.Session()
            self._client.headers["X-Consul-Token"] = self.config.consul_token or ""
        return self._client

    def register_service(self, service: Service) -> str:
        client = self._get_client()
        url = f"{self.config.consul_url}/v1/agent/service/register"

        payload = {
            "ID": service.id,
            "Name": service.name,
            "Address": service.endpoints[0].host if service.endpoints else "localhost",
            "Port": service.endpoints[0].port if service.endpoints else 8000,
            "Check": {
                "HTTP": f"http://{service.endpoints[0].host}:{service.endpoints[0].port}/health",
                "Interval": f"{self.config.health_check_interval}s",
            },
        }

        try:
            client.put(url, json=payload)
        except Exception:
            pass

        service_id = service.id or str(uuid.uuid4())
        self._services[service_id] = service
        return service_id

    def deregister_service(self, service_id: str) -> bool:
        client = self._get_client()
        url = f"{self.config.consul_url}/v1/agent/service/deregister/{service_id}"

        try:
            client.put(url)
        except Exception:
            pass

        if service_id in self._services:
            del self._services[service_id]
            return True
        return False

    def discover_services(self, name: str) -> List[Endpoint]:
        client = self._get_client()
        url = f"{self.config.consul_url}/v1/health/service/{name}"

        try:
            response = client.get(url)
            data = response.json()
            return [
                Endpoint(
                    host=s["Service"]["Address"],
                    port=s["Service"]["Port"],
                    health=s["Checks"][0]["Status"] == "passing",
                )
                for s in data
            ]
        except Exception:
            return []

    def get_load_balancer(self, name: str) -> Optional[LoadBalancer]:
        endpoints = self.discover_services(name)
        if not endpoints:
            return None
        return LoadBalancer(
            algorithm=self.config.lb_algorithm,
            backends=endpoints,
        )

    def apply_policy(self, policy: NetworkPolicy) -> bool:
        return True

    def get_dns_records(self, domain: str) -> List[DnsRecord]:
        client = self._get_client()
        url = f"{self.config.consul_url}/v1DNS/recursively/{domain}"

        try:
            response = client.get(url)
            data = response.json()
            return [
                DnsRecord(
                    name=record["Key"],
                    value=record["Value"],
                    type=record["Type"],
                    ttl=record.get("TTL", 300),
                )
                for record in data
            ]
        except Exception:
            return []
