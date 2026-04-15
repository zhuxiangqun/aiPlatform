"""
Tests for Management Base Classes
"""

import pytest
from datetime import datetime
from infra.management.base import (
    ManagementBase,
    Status,
    HealthStatus,
    Metrics,
    DiagnosisResult
)


class TestHealthStatus:
    """Tests for HealthStatus"""
    
    def test_health_status_creation(self):
        """Test creating a health status"""
        status = HealthStatus(
            status=Status.HEALTHY,
            message="All systems operational",
            details={"nodes": 5}
        )
        
        assert status.status == Status.HEALTHY
        assert status.message == "All systems operational"
        assert status.details["nodes"] == 5
        assert isinstance(status.timestamp, datetime)
    
    def test_health_status_with_timestamp(self):
        """Test creating a health status with specific timestamp"""
        timestamp = datetime(2026, 4, 11, 12, 0, 0)
        status = HealthStatus(
            status=Status.DEGRADED,
            message="Some nodes degraded",
            details={},
            timestamp=timestamp
        )
        
        assert status.timestamp == timestamp


class TestMetrics:
    """Tests for Metrics"""
    
    def test_metrics_creation(self):
        """Test creating a metric"""
        metric = Metrics(
            name="cpu_usage",
            value=0.75,
            unit="ratio",
            timestamp=datetime.now().timestamp(),
            labels={"host": "server-1"}
        )
        
        assert metric.name == "cpu_usage"
        assert metric.value == 0.75
        assert metric.unit == "ratio"
        assert metric.labels["host"] == "server-1"
    
    def test_metrics_without_labels(self):
        """Test creating a metric without labels"""
        metric = Metrics(
            name="memory_usage",
            value=0.65,
            unit="ratio",
            timestamp=datetime.now().timestamp()
        )
        
        assert metric.labels == {}


class TestDiagnosisResult:
    """Tests for DiagnosisResult"""
    
    def test_diagnosis_result_healthy(self):
        """Test creating a healthy diagnosis result"""
        result = DiagnosisResult(
            healthy=True,
            issues=[],
            recommendations=[],
            details={}
        )
        
        assert result.healthy is True
        assert len(result.issues) == 0
    
    def test_diagnosis_result_unhealthy(self):
        """Test creating an unhealthy diagnosis result"""
        result = DiagnosisResult(
            healthy=False,
            issues=["High CPU usage", "Low memory"],
            recommendations=["Scale out", "Add memory"],
            details={"cpu": 95, "memory": 15}
        )
        
        assert result.healthy is False
        assert len(result.issues) == 2
        assert len(result.recommendations) == 2
