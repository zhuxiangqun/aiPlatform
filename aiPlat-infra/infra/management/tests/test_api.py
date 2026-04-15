"""
API Tests for Management Module

Tests the REST API endpoints for infrastructure management.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from infra.management.api.main import create_app, ManagerAPI
from infra.management.manager import InfraManager
from infra.management.base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from typing import Dict, Any, List


class MockManager(ManagementBase):
    """Mock manager for testing"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._status = Status.HEALTHY
        self._healthy = True
    
    async def get_status(self) -> Status:
        return self._status
    
    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            status=Status.HEALTHY if self._healthy else Status.UNHEALTHY,
            message="Mock manager is healthy",
            details={"mock": True},
            timestamp=datetime.now()
        )
    
    async def get_metrics(self) -> List[Metrics]:
        return [
            Metrics(name="requests", value=100, unit="count", timestamp=0.0, labels={"type": "mock"}),
            Metrics(name="latency", value=50.5, unit="ms", timestamp=0.0, labels={"type": "mock"})
        ]
    
    async def diagnose(self) -> DiagnosisResult:
        return DiagnosisResult(
            healthy=self._healthy,
            issues=[],
            recommendations=["Continue monitoring"],
            details={"mock": True}
        )
    
    async def get_config(self) -> Dict[str, Any]:
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        self.config.update(config)


@pytest.fixture
def test_client():
    """Create test client"""
    manager = InfraManager()
    
    manager.register("mock1", MockManager({"name": "mock1"}))
    manager.register("mock2", MockManager({"name": "mock2"}))
    
    app = create_app(manager)
    client = TestClient(app)
    
    yield client


class TestAPIInfrastructure:
    """Test infrastructure endpoints"""
    
    def test_get_infra_status(self, test_client):
        """Test GET /api/infra/status"""
        response = test_client.get("/api/infra/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "mock1" in data["data"]
        assert "mock2" in data["data"]
    
    def test_get_infra_health(self, test_client):
        """Test GET /api/infra/health"""
        response = test_client.get("/api/infra/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "mock1" in data["data"]
        assert "mock2" in data["data"]
        
        mock1_health = data["data"]["mock1"]
        assert "status" in mock1_health
        assert "message" in mock1_health
        assert "timestamp" in mock1_health
    
    def test_get_infra_metrics(self, test_client):
        """Test GET /api/infra/metrics"""
        response = test_client.get("/api/infra/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        
        mock1_metrics = data["data"]["mock1"]
        assert len(mock1_metrics) == 2
        
        metric1 = mock1_metrics[0]
        assert metric1["name"] == "requests"
        assert metric1["value"] == 100
        assert metric1["unit"] == "count"
    
    def test_get_infra_diagnose(self, test_client):
        """Test GET /api/infra/diagnose"""
        response = test_client.get("/api/infra/diagnose")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        
        mock1_diagnosis = data["data"]["mock1"]
        assert "healthy" in mock1_diagnosis
        assert "issues" in mock1_diagnosis
        assert "recommendations" in mock1_diagnosis
        assert mock1_diagnosis["healthy"] is True


class TestAPIManagerSpecific:
    """Test manager-specific endpoints"""
    
    def test_list_managers(self, test_client):
        """Test GET /api/infra/managers"""
        response = test_client.get("/api/infra/managers")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "mock1" in data["data"]
        assert "mock2" in data["data"]
    
    def test_get_manager_status(self, test_client):
        """Test GET /api/infra/managers/{name}/status"""
        response = test_client.get("/api/infra/managers/mock1/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "mock1"
        assert "status" in data["data"]
    
    def test_get_manager_status_not_found(self, test_client):
        """Test GET /api/infra/managers/{name}/status with non-existent manager"""
        response = test_client.get("/api/infra/managers/nonexistent/status")
        
        assert response.status_code == 404
    
    def test_get_manager_health(self, test_client):
        """Test GET /api/infra/managers/{name}/health"""
        response = test_client.get("/api/infra/managers/mock1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "mock1"
        assert "health" in data["data"]
    
    def test_get_manager_metrics(self, test_client):
        """Test GET /api/infra/managers/{name}/metrics"""
        response = test_client.get("/api/infra/managers/mock1/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "mock1"
        assert len(data["data"]["metrics"]) == 2
    
    def test_get_manager_config(self, test_client):
        """Test GET /api/infra/managers/{name}/config"""
        response = test_client.get("/api/infra/managers/mock1/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "mock1"
        assert "config" in data["data"]
    
    def test_update_manager_config(self, test_client):
        """Test PUT /api/infra/managers/{name}/config"""
        update_data = {"config": {"new_key": "new_value"}}
        
        response = test_client.put(
            "/api/infra/managers/mock1/config",
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "updated" in data["message"].lower()


class TestAPIErrorHandling:
    """Test API error handling"""
    
    def test_nonexistent_manager_operations(self, test_client):
        """Test operations on non-existent manager"""
        endpoints = [
            ("/api/infra/managers/nonexistent/status", "GET"),
            ("/api/infra/managers/nonexistent/health", "GET"),
            ("/api/infra/managers/nonexistent/metrics", "GET"),
            ("/api/infra/managers/nonexistent/config", "GET"),
        ]
        
        for endpoint, method in endpoints:
            if method == "GET":
                response = test_client.get(endpoint)
            assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])