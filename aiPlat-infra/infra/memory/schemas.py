from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class MemoryRequest:
    type: str = "ram"
    size: int = 0
    tenant_id: str = ""
    priority: int = 0


@dataclass
class Allocation:
    id: str = ""
    address: int = 0
    size: int = 0
    expires_at: Optional[float] = None


@dataclass
class MemoryStats:
    total: int = 0
    used: int = 0
    available: int = 0
    cached: int = 0


@dataclass
class MemoryLimit:
    soft_limit: int = 0
    hard_limit: int = 0
    swap_limit: int = 0


@dataclass
class MemoryConfig:
    type: str = "ram"
    backend: str = "system"
    pool_enabled: bool = True
    oom_threshold: float = 0.9
