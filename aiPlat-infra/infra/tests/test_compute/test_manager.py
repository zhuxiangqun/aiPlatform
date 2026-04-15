"""
Compute Manager 单元测试

测试模块：
- LocalComputeManager
- KubernetesComputeManager（Mock测试）
- 配置类
- 数据模型
"""

import pytest
from infra.compute.manager import LocalComputeManager
from infra.compute.schemas import (
    ComputeConfig,
    ResourceRequest,
    Allocation,
    Node,
    Task,
    TaskStatus,
)


class TestComputeConfig:
    """测试配置类"""

    def test_default_config(self):
        """测试默认配置"""
        config = ComputeConfig()
        assert config is not None
        assert config.backend == "local"
        assert config.scheduling_policy == "fifo"

    def test_custom_config(self):
        """测试自定义配置"""
        config = ComputeConfig(
            backend="kubernetes",
            scheduling_policy="priority",
            default_quota={"cpu": 8, "memory": 16384},
        )
        assert config.backend == "kubernetes"
        assert config.scheduling_policy == "priority"
        assert config.default_quota["cpu"] == 8


class TestLocalComputeManager:
    """测试本地计算管理器"""

    @pytest.fixture
    def manager(self):
        """创建管理器实例"""
        config = ComputeConfig()
        return LocalComputeManager(config)

    def test_init(self, manager):
        """测试初始化"""
        assert manager is not None
        assert len(manager._nodes) == 2  # local-cpu-1, local-gpu-1

    def test_list_nodes(self, manager):
        """测试列出节点"""
        nodes = manager.list_nodes()
        assert len(nodes) == 2
        assert any(n.type == "cpu" for n in nodes)
        assert any(n.type == "gpu" for n in nodes)

    def test_list_nodes_with_filter(self, manager):
        """测试过滤节点"""
        cpu_nodes = manager.list_nodes(filters={"type": "cpu"})
        assert len(cpu_nodes) == 1
        assert cpu_nodes[0].type == "cpu"

        gpu_nodes = manager.list_nodes(filters={"type": "gpu"})
        assert len(gpu_nodes) == 1
        assert gpu_nodes[0].type == "gpu"

        ready_nodes = manager.list_nodes(filters={"status": "ready"})
        assert len(ready_nodes) == 2

    def test_get_node(self, manager):
        """测试获取节点"""
        cpu_node = manager.get_node("local-cpu-1")
        assert cpu_node is not None
        assert cpu_node.type == "cpu"
        assert cpu_node.status == "ready"

    def test_get_node_not_found(self, manager):
        """测试获取不存在的节点"""
        node = manager.get_node("nonexistent")
        assert node is None

    def test_allocate(self, manager):
        """测试资源分配"""
        request = ResourceRequest(resource_type="cpu", quantity=4)
        allocation = manager.allocate(request)

        assert allocation is not None
        assert allocation.id is not None
        assert "cpu" in allocation.resources
        assert allocation.resources["cpu"] == 4

    def test_allocate_gpu(self, manager):
        """测试GPU资源分配"""
        request = ResourceRequest(resource_type="gpu", quantity=1)
        allocation = manager.allocate(request)

        assert allocation is not None
        assert "gpu" in allocation.resources
        assert allocation.resources["gpu"] == 1

    def test_release(self, manager):
        """测试资源释放"""
        request = ResourceRequest(resource_type="cpu", quantity=4)
        allocation = manager.allocate(request)

        result = manager.release(allocation.id)
        assert result is True
        assert allocation.id not in manager._allocations

    def test_release_not_found(self, manager):
        """测试释放不存在的分配"""
        result = manager.release("nonexistent")
        assert result is False

    def test_submit_task(self, manager):
        """测试提交任务"""
        task = Task(
            command="python train.py",
            resources={"cpu": 2, "memory": 4096},
        )
        task_id = manager.submit_task(task)

        assert task_id is not None
        task_status = manager.get_task_status(task_id)
        assert task_status is not None
        assert task_status.state == "pending"

    def test_get_task_status(self, manager):
        """测试获取任务状态"""
        task = Task(command="python train.py")
        task_id = manager.submit_task(task)

        status = manager.get_task_status(task_id)
        assert status is not None
        assert status.id == task_id
        assert status.state == "pending"
        assert status.progress == 0.0

    def test_get_task_status_not_found(self, manager):
        """测试获取不存在的任务状态"""
        status = manager.get_task_status("nonexistent")
        assert status is None

    def test_cancel_task(self, manager):
        """测试取消任务"""
        task = Task(command="python train.py")
        task_id = manager.submit_task(task)

        result = manager.cancel_task(task_id)
        assert result is True

        status = manager.get_task_status(task_id)
        assert status.state == "cancelled"

    def test_cancel_task_not_found(self, manager):
        """测试取消不存在的任务"""
        result = manager.cancel_task("nonexistent")
        assert result is False


class TestComputeSchema:
    """测试数据模型"""

    def test_resource_request(self):
        """测试资源请求"""
        request = ResourceRequest(resource_type="cpu", quantity=4)
        assert request.resource_type == "cpu"
        assert request.quantity == 4

    def test_allocation(self):
        """测试资源分配"""
        allocation = Allocation(id="test-1", node_id="node-1", resources={"cpu": 4})
        assert allocation.id == "test-1"
        assert allocation.node_id == "node-1"
        assert allocation.resources["cpu"] == 4

    def test_node(self):
        """测试节点"""
        node = Node(
            id="node-1",
            type="cpu",
            status="ready",
            capacity={"cpu": 8, "memory": 16384},
            available={"cpu": 8, "memory": 16384},
        )
        assert node.id == "node-1"
        assert node.type == "cpu"
        assert node.status == "ready"

    def test_task(self):
        """测试任务"""
        task = Task(
            command="python train.py --epochs 100",
            resources={"cpu": 4, "memory": 8192},
        )
        assert task.command == "python train.py --epochs 100"
        assert task.resources["cpu"] == 4

    def test_task_status(self):
        """测试任务状态"""
        status = TaskStatus(
            id="task-123",
            state="running",
            progress=50.0,
        )
        assert status.id == "task-123"
        assert status.state == "running"
        assert status.progress == 50.0
