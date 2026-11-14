"""计算资源分配与任务调度抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from .schemas import ResourceRequest, Allocation, Node, Task, TaskStatus


class ComputeManager(ABC):
    """计算节点分配与任务提交抽象。"""

    @abstractmethod
    def allocate(self, resource_request: ResourceRequest) -> Allocation:
        """按请求分配计算资源。

        Args:
            resource_request: 资源需求。
        """
        pass

    @abstractmethod
    def release(self, allocation_id: str) -> bool:
        """释放已分配资源。

        Args:
            allocation_id: 分配 ID。
        """
        pass

    @abstractmethod
    def list_nodes(self, filters: Dict = None) -> List[Node]:
        """列出计算节点。

        Args:
            filters: 可选过滤条件。
        """
        pass

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[Node]:
        """获取单个节点。

        Args:
            node_id: 节点 ID。
        """
        pass

    @abstractmethod
    def submit_task(self, task: Task) -> str:
        """提交计算任务，返回 task_id。

        Args:
            task: 任务描述。
        """
        pass

    @abstractmethod
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """查询任务状态。

        Args:
            task_id: 任务 ID。
        """
        pass

    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """取消任务。

        Args:
            task_id: 任务 ID。
        """
        pass
