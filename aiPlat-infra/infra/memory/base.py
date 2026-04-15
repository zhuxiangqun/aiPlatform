from abc import ABC, abstractmethod
from typing import Optional
from .schemas import MemoryRequest, Allocation, MemoryStats, MemoryLimit


class MemoryManager(ABC):
    @abstractmethod
    def allocate(self, request: MemoryRequest) -> Allocation:
        pass

    @abstractmethod
    def release(self, allocation_id: str) -> bool:
        pass

    @abstractmethod
    def get_stats(self, node_id: str) -> MemoryStats:
        pass

    @abstractmethod
    def set_limit(self, tenant_id: str, limit: MemoryLimit) -> bool:
        pass

    @abstractmethod
    def enable_oom_protection(self, threshold: float) -> bool:
        pass

    @abstractmethod
    def compact(self, node_id: str) -> bool:
        pass
