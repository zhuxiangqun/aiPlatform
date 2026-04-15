from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from .schemas import ResourceRequest, Allocation, Node, Task, TaskStatus


class ComputeManager(ABC):
    @abstractmethod
    def allocate(self, resource_request: ResourceRequest) -> Allocation:
        pass

    @abstractmethod
    def release(self, allocation_id: str) -> bool:
        pass

    @abstractmethod
    def list_nodes(self, filters: Dict = None) -> List[Node]:
        pass

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[Node]:
        pass

    @abstractmethod
    def submit_task(self, task: Task) -> str:
        pass

    @abstractmethod
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        pass

    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        pass
