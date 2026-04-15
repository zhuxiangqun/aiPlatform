"""
Tests for Node Manager
"""

import pytest
from infra.management.node.manager import NodeManager
from infra.management.base import Status


class TestNodeManager:
    """Tests for Node Manager"""
    
    @pytest.fixture
    def manager(self):
        """Create node manager"""
        config = {
            "kubernetes_api": "https://k8s-api.example.com",
            "driver_versions": ["535.54.03", "535.104.05"],
            "auto_drain_before_upgrade": True
        }
        return NodeManager(config)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test get status"""
        status = await manager.get_status()
        assert isinstance(status, Status)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, manager):
        """Test get metrics"""
        metrics = await manager.get_metrics()
        assert isinstance(metrics, list)
    
    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        """Test health check"""
        health = await manager.health_check()
        assert isinstance(health.status, Status)
        assert health.message
    
    @pytest.mark.asyncio
    async def test_diagnose(self, manager):
        """Test diagnose"""
        diagnosis = await manager.diagnose()
        assert isinstance(diagnosis.healthy, bool)
        assert isinstance(diagnosis.issues, list)
        assert isinstance(diagnosis.recommendations, list)
    
    @pytest.mark.asyncio
    async def test_add_node(self, manager):
        """Test add node"""
        node = await manager.add_node({
            "name": "test-node-01",
            "ip": "10.0.0.1",
            "gpu_model": "A100",
            "gpu_count": 4,
            "driver_version": "535.54.03"
        })
        assert node.name == "test-node-01"
        assert node.gpu_count == 4
        assert node.status == "Ready"
    
    @pytest.mark.asyncio
    async def test_list_nodes(self, manager):
        """Test list nodes"""
        await manager.add_node({"name": "node-01", "gpu_count": 4})
        await manager.add_node({"name": "node-02", "gpu_count": 2})
        
        nodes = await manager.list_nodes()
        assert len(nodes) == 2
    
    @pytest.mark.asyncio
    async def test_get_node(self, manager):
        """Test get node"""
        await manager.add_node({"name": "node-01", "gpu_count": 4})
        
        node = await manager.get_node("node-01")
        assert node is not None
        assert node.name == "node-01"
    
    @pytest.mark.asyncio
    async def test_remove_node(self, manager):
        """Test remove node"""
        await manager.add_node({"name": "node-01", "gpu_count": 4})
        await manager.remove_node("node-01")
        
        node = await manager.get_node("node-01")
        assert node is None
    
    @pytest.mark.asyncio
    async def test_drain_node(self, manager):
        """Test drain node"""
        await manager.add_node({"name": "node-01", "gpu_count": 4})
        await manager.drain_node("node-01")
        
        node = await manager.get_node("node-01")
        assert node.status == "Draining"
    
    @pytest.mark.asyncio
    async def test_restart_node(self, manager):
        """Test restart node"""
        await manager.add_node({"name": "node-01", "gpu_count": 4})
        await manager.restart_node("node-01")
        
        node = await manager.get_node("node-01")
        assert node.status == "Restarting"
    
    @pytest.mark.asyncio
    async def test_get_driver_version(self, manager):
        """Test get driver version"""
        await manager.add_node({"name": "node-01", "driver_version": "535.54.03"})
        
        version = await manager.get_driver_version("node-01")
        assert version == "535.54.03"
    
    @pytest.mark.asyncio
    async def test_upgrade_driver(self, manager):
        """Test upgrade driver"""
        await manager.add_node({"name": "node-01", "driver_version": "535.54.03"})
        await manager.upgrade_driver("node-01", "535.104.05")
        
        node = await manager.get_node("node-01")
        assert node.driver_version == "535.104.05"
    
    @pytest.mark.asyncio
    async def test_update_node_labels(self, manager):
        """Test update node labels"""
        await manager.add_node({"name": "node-01", "labels": {"gpu": "true"}})
        await manager.update_node_labels("node-01", {"node-type": "gpu"})
        
        node = await manager.get_node("node-01")
        assert node.labels["node-type"] == "gpu"
    
    @pytest.mark.asyncio
    async def test_get_config(self, manager):
        """Test get config"""
        config = await manager.get_config()
        assert "kubernetes_api" in config
        assert "driver_versions" in config
    
    @pytest.mark.asyncio
    async def test_update_config(self, manager):
        """Test update config"""
        await manager.update_config({"kubernetes_api": "https://new-api.example.com"})
        config = await manager.get_config()
        assert config["kubernetes_api"] == "https://new-api.example.com"


class TestServiceManager:
    """Tests for Service Manager"""
    
    @pytest.fixture
    def manager(self):
        """Create service manager"""
        config = {
            "kubernetes_api": "https://k8s-api.example.com",
            "default_namespace": "ai-prod"
        }
        from infra.management.service.manager import ServiceManager
        return ServiceManager(config)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test get status"""
        status = await manager.get_status()
        assert isinstance(status, Status)
    
    @pytest.mark.asyncio
    async def test_deploy_service(self, manager):
        """Test deploy service"""
        service = await manager.deploy_service({
            "name": "test-service",
            "namespace": "ai-prod",
            "image": "vllm/vllm:latest",
            "replicas": 4,
            "gpu_count": 4
        })
        assert service.name == "test-service"
        assert service.replicas == 4
    
    @pytest.mark.asyncio
    async def test_list_services(self, manager):
        """Test list services"""
        await manager.deploy_service({"name": "service-01"})
        await manager.deploy_service({"name": "service-02"})
        
        services = await manager.list_services()
        assert len(services) == 2
    
    @pytest.mark.asyncio
    async def test_scale_service(self, manager):
        """Test scale service"""
        await manager.deploy_service({"name": "service-01", "replicas": 2})
        await manager.scale_service("service-01", 4)
        
        service = await manager.get_service("service-01")
        assert service.replicas == 4
    
    @pytest.mark.asyncio
    async def test_stop_service(self, manager):
        """Test stop service"""
        await manager.deploy_service({"name": "service-01"})
        await manager.stop_service("service-01")
        
        service = await manager.get_service("service-01")
        assert service.status == "Stopped"


class TestSchedulerManager:
    """Tests for Scheduler Manager"""
    
    @pytest.fixture
    def manager(self):
        """Create scheduler manager"""
        config = {
            "kubernetes_api": "https://k8s-api.example.com",
            "default_scheduler": "default-scheduler"
        }
        from infra.management.scheduler.manager import SchedulerManager
        return SchedulerManager(config)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test get status"""
        status = await manager.get_status()
        assert isinstance(status, Status)
    
    @pytest.mark.asyncio
    async def test_create_quota(self, manager):
        """Test create quota"""
        quota = await manager.create_quota({
            "name": "test-quota",
            "gpu_quota": 8,
            "team": "test-team"
        })
        assert quota.name == "test-quota"
        assert quota.gpu_quota == 8
    
    @pytest.mark.asyncio
    async def test_list_quotas(self, manager):
        """Test list quotas"""
        await manager.create_quota({"name": "quota-01", "gpu_quota": 4})
        await manager.create_quota({"name": "quota-02", "gpu_quota": 8})
        
        quotas = await manager.list_quotas()
        assert len(quotas) == 2
    
    @pytest.mark.asyncio
    async def test_create_policy(self, manager):
        """Test create policy"""
        policy = await manager.create_policy({
            "name": "test-policy",
            "priority": 100,
            "type": "high-priority"
        })
        assert policy.name == "test-policy"
        assert policy.priority == 100
    
    @pytest.mark.asyncio
    async def test_submit_task(self, manager):
        """Test submit task"""
        task = await manager.submit_task({
            "name": "test-task",
            "gpu_count": 4,
            "queue": "default"
        })
        assert task.name == "test-task"
        assert task.status == "pending"
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, manager):
        """Test cancel task"""
        await manager.submit_task({"name": "task-01"})
        await manager.cancel_task("task-01")
        
        task = await manager.get_task("task-01")
        assert task.status == "cancelled"
    
    @pytest.mark.asyncio
    async def test_get_queue_status(self, manager):
        """Test get queue status"""
        await manager.submit_task({"name": "task-01", "queue": "default"})
        await manager.submit_task({"name": "task-02", "queue": "default"})
        
        status = await manager.get_queue_status("default")
        assert status["queue"] == "default"
        assert status["total_tasks"] == 2
    
    @pytest.mark.asyncio
    async def test_create_autoscaling(self, manager):
        """Test create autoscaling policy"""
        policy = await manager.create_autoscaling({
            "service": "test-service",
            "min_replicas": 2,
            "max_replicas": 10
        })
        assert policy.service == "test-service"
        assert policy.min_replicas == 2