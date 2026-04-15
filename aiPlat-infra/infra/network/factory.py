from typing import Optional
from .schemas import NetworkConfig
from .base import NetworkManager


def create_network_manager(config: Optional[NetworkConfig] = None) -> NetworkManager:
    config = config or NetworkConfig()

    if config.backend == "static":
        from .manager import StaticNetworkManager

        return StaticNetworkManager(config)
    elif config.backend == "consul":
        from .manager import ConsulNetworkManager

        return ConsulNetworkManager(config)
    else:
        raise ValueError(f"Unknown network backend: {config.backend}")
