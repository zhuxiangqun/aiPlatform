from typing import Optional
from .schemas import ComputeConfig
from .base import ComputeManager


def create_compute_manager(config: Optional[ComputeConfig] = None) -> ComputeManager:
    config = config or ComputeConfig()

    if config.backend == "local":
        from .manager import LocalComputeManager

        return LocalComputeManager(config)
    elif config.backend == "kubernetes":
        from .manager import KubernetesComputeManager

        return KubernetesComputeManager(config)
    else:
        raise ValueError(f"Unknown compute backend: {config.backend}")
