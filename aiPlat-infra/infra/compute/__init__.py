from .base import ComputeManager
from .schemas import (
    ComputeConfig,
    ResourceRequest,
    Allocation,
    Node,
    Task,
    TaskStatus,
)
from .factory import create_compute_manager

__all__ = [
    "ComputeManager",
    "ComputeConfig",
    "ResourceRequest",
    "Allocation",
    "Node",
    "Task",
    "TaskStatus",
    "create_compute_manager",
]

try:
    from .manager import LocalComputeManager, KubernetesComputeManager

    __all__.extend(["LocalComputeManager", "KubernetesComputeManager"])
except ImportError:
    pass
