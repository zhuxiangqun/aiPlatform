"""memory/base：内存管理抽象接口。"""

from abc import ABC, abstractmethod
from typing import Optional
from .schemas import MemoryRequest, Allocation, MemoryStats, MemoryLimit


class MemoryManager(ABC):
    """内存管理器抽象接口。"""

    @abstractmethod
    def allocate(self, request: MemoryRequest) -> Allocation:
        """分配内存。

        Args:
            request: 内存请求。
        """
        pass

    @abstractmethod
    def release(self, allocation_id: str) -> bool:
        """释放分配。

        Args:
            allocation_id: 分配 ID。
        """
        pass

    @abstractmethod
    def get_stats(self, node_id: str) -> MemoryStats:
        """获取节点内存统计。

        Args:
            node_id: 节点 ID。
        """
        pass

    @abstractmethod
    def set_limit(self, tenant_id: str, limit: MemoryLimit) -> bool:
        """设置租户内存上限。

        Args:
            tenant_id: 租户 ID。
            limit: 内存上限。
        """
        pass

    @abstractmethod
    def enable_oom_protection(self, threshold: float) -> bool:
        """启用 OOM 保护。

        Args:
            threshold: 触发阈值。
        """
        pass

    @abstractmethod
    def compact(self, node_id: str) -> bool:
        """压缩节点内存。

        Args:
            node_id: 节点 ID。
        """
        pass
