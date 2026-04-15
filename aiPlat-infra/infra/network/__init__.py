from .base import NetworkManager
from .schemas import (
    NetworkConfig,
    Service,
    Endpoint,
    LoadBalancer,
    NetworkPolicy,
    DnsRecord,
)
from .factory import create_network_manager

__all__ = [
    "NetworkManager",
    "NetworkConfig",
    "Service",
    "Endpoint",
    "LoadBalancer",
    "NetworkPolicy",
    "DnsRecord",
    "create_network_manager",
]

try:
    from .manager import StaticNetworkManager, ConsulNetworkManager

    __all__.extend(["StaticNetworkManager", "ConsulNetworkManager"])
except ImportError:
    pass
