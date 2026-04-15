from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Service:
    name: str = ""
    endpoints: List["Endpoint"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_check: Optional[Dict[str, Any]] = None


@dataclass
class Endpoint:
    address: str = ""
    port: int = 0
    weight: int = 1
    health: bool = True


@dataclass
class LoadBalancer:
    algorithm: str = "round_robin"
    backends: List[Endpoint] = field(default_factory=list)
    health_check: Optional[Dict[str, Any]] = None


@dataclass
class NetworkPolicy:
    type: str = ""
    rules: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 0


@dataclass
class DnsRecord:
    name: str = ""
    type: str = "A"
    value: str = ""
    ttl: int = 300


@dataclass
class NetworkConfig:
    backend: str = "static"
    lb_algorithm: str = "round_robin"
    health_check_interval: int = 10
    consul_url: str = "http://localhost:8500"
    consul_token: Optional[str] = None
    etcd_endpoints: List[str] = field(default_factory=list)
