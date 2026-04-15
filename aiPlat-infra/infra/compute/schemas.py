from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ResourceRequest:
    resource_type: str = "cpu"
    quantity: int = 1
    priority: int = 0


@dataclass
class Allocation:
    id: str = ""
    node_id: str = ""
    resources: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[float] = None


@dataclass
class Node:
    id: str = ""
    type: str = ""
    status: str = ""
    capacity: Dict[str, int] = field(default_factory=dict)
    available: Dict[str, int] = field(default_factory=dict)


@dataclass
class Task:
    id: str = ""
    command: str = ""
    resources: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 0


@dataclass
class TaskStatus:
    id: str = ""
    state: str = ""
    progress: float = 0.0
    result: Optional[Any] = None


@dataclass
class KubernetesConfig:
    group: str = "ai-platform.io"
    version: str = "v1"
    plural: str = "resources"
    namespace: str = "default"


@dataclass
class ComputeConfig:
    backend: str = "local"
    default_quota: Dict[str, int] = field(default_factory=dict)
    scheduling_policy: str = "fifo"
    k8s: Optional[KubernetesConfig] = None
