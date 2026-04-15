import uuid
from typing import List, Optional, Dict
from .base import ComputeManager
from .schemas import ResourceRequest, Allocation, Node, Task, TaskStatus, ComputeConfig


class LocalComputeManager(ComputeManager):
    def __init__(self, config: ComputeConfig):
        self.config = config
        self._allocations: Dict[str, Allocation] = {}
        self._nodes: Dict[str, Node] = {}
        self._tasks: Dict[str, TaskStatus] = {}
        self._init_local_nodes()

    def _init_local_nodes(self):
        self._nodes["local-cpu-1"] = Node(
            id="local-cpu-1",
            type="cpu",
            status="ready",
            capacity={"cpu": 8, "memory": 16384},
            available={"cpu": 8, "memory": 16384},
        )
        self._nodes["local-gpu-1"] = Node(
            id="local-gpu-1",
            type="gpu",
            status="ready",
            capacity={"gpu": 1, "cpu": 4, "memory": 8192},
            available={"gpu": 1, "cpu": 4, "memory": 8192},
        )

    def allocate(self, resource_request: ResourceRequest) -> Allocation:
        allocation = Allocation(
            id=str(uuid.uuid4()),
            node_id=f"local-{resource_request.resource_type}-1",
            resources={resource_request.resource_type: resource_request.quantity},
        )
        self._allocations[allocation.id] = allocation
        return allocation

    def release(self, allocation_id: str) -> bool:
        if allocation_id in self._allocations:
            del self._allocations[allocation_id]
            return True
        return False

    def list_nodes(self, filters: Dict = None) -> List[Node]:
        nodes = list(self._nodes.values())
        if filters:
            if "type" in filters:
                nodes = [n for n in nodes if n.type == filters["type"]]
            if "status" in filters:
                nodes = [n for n in nodes if n.status == filters["status"]]
        return nodes

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def submit_task(self, task: Task) -> str:
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskStatus(
            id=task_id,
            state="pending",
            progress=0.0,
        )
        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].state = "cancelled"
            return True
        return False


class KubernetesComputeManager(ComputeManager):
    def __init__(self, config: ComputeConfig):
        self.config = config
        self._client = None
        self._allocations: Dict[str, Allocation] = {}
        self._tasks: Dict[str, TaskStatus] = {}

    def _get_client(self):
        if self._client is None:
            from kubernetes import client, config as k8s_config

            try:
                k8s_config.load_kube_config()
            except Exception:
                k8s_config.load_incluster_config()
            self._client = client
        return self._client

    def allocate(self, resource_request: ResourceRequest) -> Allocation:
        client = self._get_client()
        api = client.CustomObjectsApi()

        group = self.config.k8s.group or "ai-platform.io"
        version = self.config.k8s.version or "v1"
        plural = self.config.k8s.plural or "resources"

        try:
            resource = api.get_custom_object(
                group, version, "", plural, resource_request.resource_type
            )
            allocation = Allocation(
                id=str(uuid.uuid4()),
                node_id=resource.get("status", {}).get("node"),
                resources={resource_request.resource_type: resource_request.quantity},
            )
            self._allocations[allocation.id] = allocation
            return allocation
        except Exception:
            allocation = Allocation(
                id=str(uuid.uuid4()),
                node_id="k8s-pool",
                resources={resource_request.resource_type: resource_request.quantity},
            )
            self._allocations[allocation.id] = allocation
            return allocation

    def release(self, allocation_id: str) -> bool:
        if allocation_id in self._allocations:
            del self._allocations[allocation_id]
            return True
        return False

    def list_nodes(self, filters: Dict = None) -> List[Node]:
        client = self._get_client()
        api = client.CoreV1Api()

        try:
            nodes = api.list_node()
            result = []
            for n in nodes.items:
                result.append(
                    Node(
                        id=n.metadata.name,
                        type="gpu" if "gpu" in n.metadata.labels else "cpu",
                        status=n.status.conditions[-1].type
                        if n.status.conditions
                        else "Unknown",
                        capacity=n.status.capacity or {},
                        available=n.status.allocatable or {},
                    )
                )
            return result
        except Exception:
            return []

    def get_node(self, node_id: str) -> Optional[Node]:
        client = self._get_client()
        api = client.CoreV1Api()

        try:
            n = api.read_node(node_id)
            return Node(
                id=n.metadata.name,
                type="gpu" if "gpu" in n.metadata.labels else "cpu",
                status=n.status.conditions[-1].type
                if n.status.conditions
                else "Unknown",
                capacity=n.status.capacity or {},
                available=n.status.allocatable or {},
            )
        except Exception:
            return None

    def submit_task(self, task: Task) -> str:
        client = self._get_client()
        api = client.CustomObjectsApi()

        group = self.config.k8s.group or "ai-platform.io"
        version = self.config.k8s.version or "v1"
        plural = self.config.k8s.plural or "tasks"

        task_id = str(uuid.uuid4())
        task_obj = {
            "apiVersion": f"{group}/{version}",
            "kind": "Task",
            "metadata": {"name": task_id},
            "spec": {
                "image": task.image,
                "command": task.command,
                "env": task.env,
            },
        }

        try:
            api.create_custom_object(group, version, "", plural, task_obj)
        except Exception:
            pass

        self._tasks[task_id] = TaskStatus(id=task_id, state="pending", progress=0.0)
        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        if task_id in self._tasks:
            return self._tasks[task_id]

        client = self._get_client()
        api = client.CustomObjectsApi()

        group = self.config.k8s.group or "ai-platform.io"
        version = self.config.k8s.version or "v1"
        plural = self.config.k8s.plural or "tasks"

        try:
            task = api.get_custom_object(group, version, "", plural, task_id)
            return TaskStatus(
                id=task_id,
                state=task.get("status", {}).get("phase", "Unknown"),
                progress=task.get("status", {}).get("progress", 0.0),
            )
        except Exception:
            return None

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].state = "cancelled"
            return True

        client = self._get_client()
        api = client.CustomObjectsApi()

        group = self.config.k8s.group or "ai-platform.io"
        version = self.config.k8s.version or "v1"
        plural = self.config.k8s.plural or "tasks"

        try:
            api.delete_custom_object(group, version, "", plural, task_id)
            return True
        except Exception:
            return False
