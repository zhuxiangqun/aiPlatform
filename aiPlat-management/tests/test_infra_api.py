"""
Tests for Infrastructure API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from management.server import create_app


@pytest.fixture
def client():
    """Create test client"""
    app = create_app()
    return TestClient(app)


class TestNodesAPI:
    """Test nodes API endpoints"""
    
    def test_list_nodes(self, client):
        """Test list nodes endpoint"""
        response = client.get("/api/infra/nodes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_node(self, client):
        """Test get single node endpoint"""
        response = client.get("/api/infra/nodes/node-01")
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "name" in data
    
    def test_add_node(self, client):
        """Test add node endpoint"""
        node_data = {
            "name": "test-node",
            "ip": "192.168.1.100",
            "gpu_model": "A100",
            "gpu_count": 4,
            "driver_version": "525.60.13"
        }
        response = client.post("/api/infra/nodes", json=node_data)
        assert response.status_code in [200, 201]
    
    def test_drain_node(self, client):
        """Test drain node endpoint"""
        response = client.post("/api/infra/nodes/node-01/drain")
        assert response.status_code in [200, 404]
    
    def test_restart_node(self, client):
        """Test restart node endpoint"""
        response = client.post("/api/infra/nodes/node-01/restart")
        assert response.status_code in [200, 404]


class TestServicesAPI:
    """Test services API endpoints"""
    
    def test_list_services(self, client):
        """Test list services endpoint"""
        response = client.get("/api/infra/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_deploy_service(self, client):
        """Test deploy service endpoint"""
        service_data = {
            "name": "test-service",
            "image": "vllm/vllm-openai",
            "replicas": 2,
            "gpu_count": 1,
            "gpu_type": "A100",
            "namespace": "ai-prod"
        }
        response = client.post("/api/infra/services", json=service_data)
        assert response.status_code in [200, 201]
    
    def test_scale_service(self, client):
        """Test scale service endpoint"""
        response = client.post("/api/infra/services/test-service/scale?replicas=4")
        assert response.status_code in [200, 404, 422]
    
    def test_get_service_logs(self, client):
        """Test get service logs endpoint"""
        response = client.get("/api/infra/services/test-service/logs")
        assert response.status_code in [200, 404]


class TestQuotasAPI:
    """Test quotas API endpoints"""
    
    def test_list_quotas(self, client):
        """Test list quotas endpoint"""
        response = client.get("/api/infra/scheduler/quotas")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_quota(self, client):
        """Test create quota endpoint"""
        quota_data = {
            "name": "test-quota",
            "gpu_quota": 8,
            "team": "test-team"
        }
        response = client.post("/api/infra/scheduler/quotas", json=quota_data)
        assert response.status_code in [200, 201]
    
    def test_update_quota(self, client):
        """Test update quota endpoint"""
        response = client.put("/api/infra/scheduler/quotas/test-quota", json={"gpu_quota": 16})
        assert response.status_code in [200, 404]


class TestTasksAPI:
    """Test tasks API endpoints"""
    
    def test_list_tasks(self, client):
        """Test list tasks endpoint"""
        response = client.get("/api/infra/scheduler/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_submit_task(self, client):
        """Test submit task endpoint"""
        task_data = {
            "name": "test-task",
            "gpu_count": 4,
            "gpu_type": "A100",
            "queue": "high",
            "priority": 100
        }
        response = client.post("/api/infra/scheduler/tasks", json=task_data)
        assert response.status_code in [200, 201]


class TestStorageAPI:
    """Test storage API endpoints"""
    
    def test_list_collections(self, client):
        """Test list vector collections endpoint"""
        response = client.get("/api/infra/storage/vector/collections")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_models(self, client):
        """Test list models endpoint"""
        response = client.get("/api/infra/storage/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_pvc(self, client):
        """Test list PVC endpoint"""
        response = client.get("/api/infra/storage/pvc")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestNetworkAPI:
    """Test network API endpoints"""
    
    def test_list_network_services(self, client):
        """Test list network services endpoint"""
        response = client.get("/api/infra/network/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_ingress(self, client):
        """Test list ingress endpoint"""
        response = client.get("/api/infra/network/ingress")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_network_policies(self, client):
        """Test list network policies endpoint"""
        response = client.get("/api/infra/network/policies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMonitoringAPI:
    """Test monitoring API endpoints"""
    
    def test_get_monitoring_overview(self, client):
        """Test get monitoring overview endpoint"""
        response = client.get("/api/infra/monitoring/overview")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "gpus" in data
    
    def test_get_metrics(self, client):
        """Test get metrics endpoint"""
        response = client.get("/api/infra/monitoring/metrics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_alerts(self, client):
        """Test list alerts endpoint"""
        response = client.get("/api/infra/monitoring/alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_audit_logs(self, client):
        """Test list audit logs endpoint"""
        response = client.get("/api/infra/monitoring/audit-logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)