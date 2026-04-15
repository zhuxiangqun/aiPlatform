"""
Prometheus Integration Tests

Tests the Prometheus metrics exporter.
"""

import pytest
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from infra.management.monitoring.prometheus import (
    PrometheusMetric,
    PrometheusCollector,
    ManagementMetricsExporter,
    MetricsMiddleware
)
from infra.management.base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from typing import Dict, Any, List


class TestPrometheusMetric:
    """Test PrometheusMetric class"""
    
    def test_create_metric(self):
        """Test creating a metric"""
        metric = PrometheusMetric(
            name="test_metric",
            metric_type="gauge",
            help_text="Test metric",
            labels={"service": "test"}
        )
        
        assert metric.name == "test_metric"
        assert metric.metric_type == "gauge"
        assert metric.help_text == "Test metric"
        assert metric.labels == {"service": "test"}
    
    def test_set_value(self):
        """Test setting metric value"""
        metric = PrometheusMetric(name="test_metric")
        metric.set_value(42.5)
        
        assert metric.value == 42.5
    
    def test_to_prometheus_format_without_labels(self):
        """Test Prometheus format without labels"""
        metric = PrometheusMetric(
            name="test_metric",
            metric_type="gauge",
            help_text="Test metric"
        )
        metric.set_value(100)
        
        output = metric.to_prometheus_format()
        
        assert "# HELP test_metric Test metric" in output
        assert "# TYPE test_metric gauge" in output
        assert "test_metric 100" in output
    
    def test_to_prometheus_format_with_labels(self):
        """Test Prometheus format with labels"""
        metric = PrometheusMetric(
            name="test_metric",
            metric_type="counter",
            help_text="Test metric",
            labels={"service": "test", "env": "dev"}
        )
        metric.set_value(50)
        
        output = metric.to_prometheus_format()
        
        assert 'service="test"' in output
        assert 'env="dev"' in output
        assert "test_metric{service=\"test\",env=\"dev\"} 50" in output


class TestPrometheusCollector:
    """Test PrometheusCollector class"""
    
    def test_create_collector(self):
        """Test creating a collector"""
        collector = PrometheusCollector(namespace="test")
        
        assert collector.namespace == "test"
        assert len(collector._metrics) == 0
    
    def test_register_metric(self):
        """Test registering a metric"""
        collector = PrometheusCollector(namespace="test")
        
        metric = collector.register_metric(
            name="requests",
            metric_type="counter",
            help_text="Total requests"
        )
        
        assert "test_requests" in collector._metrics
        assert metric.name == "test_requests"
    
    def test_update_metric(self):
        """Test updating a metric"""
        collector = PrometheusCollector(namespace="test")
        
        collector.update_metric("requests", 100)
        
        metric = collector.get_metric("requests")
        assert metric is not None
        assert metric.value == 100
    
    def test_collect(self):
        """Test collecting metrics"""
        collector = PrometheusCollector(namespace="test")
        
        collector.register_metric("metric1", help_text="First metric")
        collector.register_metric("metric2", help_text="Second metric")
        collector.update_metric("metric1", 10)
        collector.update_metric("metric2", 20)
        
        output = collector.collect()
        
        assert "test_metric1" in output
        assert "test_metric2" in output
        assert " 10" in output
        assert " 20" in output
    
    def test_clear(self):
        """Test clearing metrics"""
        collector = PrometheusCollector(namespace="test")
        
        collector.register_metric("test", help_text="Test")
        assert len(collector._metrics) == 1
        
        collector.clear()
        assert len(collector._metrics) == 0


class TestManagementMetricsExporter:
    """Test ManagementMetricsExporter class"""
    
    def test_create_exporter(self):
        """Test creating an exporter"""
        exporter = ManagementMetricsExporter(namespace="test")
        
        assert exporter.collector.namespace == "test"
        assert len(exporter.collector._metrics) > 0
    
    def test_default_metrics_configured(self):
        """Test that default metrics are configured"""
        exporter = ManagementMetricsExporter()
        
        assert exporter.collector.get_metric("manager_status") is not None
        assert exporter.collector.get_metric("manager_health") is not None
        assert exporter.collector.get_metric("manager_operations_total") is not None
        assert exporter.collector.get_metric("manager_errors_total") is not None
    
    def test_get_prometheus_output(self):
        """Test getting Prometheus output"""
        exporter = ManagementMetricsExporter()
        
        exporter.collector.update_metric("manager_status", 1.0)
        
        output = exporter.get_prometheus_output()
        
        assert "# TYPE aiplat_infra_manager_status gauge" in output
    
    @pytest.mark.asyncio
    async def test_export_from_manager(self):
        """Test exporting from manager"""
        exporter = ManagementMetricsExporter()
        
        class MockManager(ManagementBase):
            async def get_status(self) -> Status:
                return Status.HEALTHY
            
            async def health_check(self) -> HealthStatus:
                return HealthStatus(
                    status=Status.HEALTHY,
                    message="OK",
                    details={},
                    timestamp=datetime.now()
                )
            
            async def get_metrics(self) -> List[Metrics]:
                return [Metrics(name="requests", value=100, unit="count", timestamp=0.0)]
            
            async def diagnose(self) -> DiagnosisResult:
                return DiagnosisResult(healthy=True, issues=[], recommendations=[])
            
            async def get_config(self) -> Dict[str, Any]:
                return {}
            
            async def update_config(self, config: Dict[str, Any]) -> None:
                pass
        
        manager = MockManager({})
        metrics_data = await exporter.export_from_manager("test_manager", manager)
        
        assert "status" in metrics_data
        assert "health" in metrics_data


class TestMetricsMiddleware:
    """Test MetricsMiddleware class"""
    
    def test_create_middleware(self):
        """Test creating middleware"""
        exporter = ManagementMetricsExporter()
        middleware = MetricsMiddleware(exporter)
        
        assert middleware.exporter == exporter
        assert middleware._request_count == 0
        assert middleware._error_count == 0
    
    @pytest.mark.asyncio
    async def test_track_request(self):
        """Test tracking requests"""
        exporter = ManagementMetricsExporter()
        middleware = MetricsMiddleware(exporter)
        
        await middleware.track_request("test_manager", "get_status")
        await middleware.track_request("test_manager", "health_check")
        
        assert middleware._request_count == 2
    
    @pytest.mark.asyncio
    async def test_track_error(self):
        """Test tracking errors"""
        exporter = ManagementMetricsExporter()
        middleware = MetricsMiddleware(exporter)
        
        await middleware.track_error("test_manager", "ConnectionError")
        
        assert middleware._error_count == 1
    
    def test_get_stats(self):
        """Test getting statistics"""
        exporter = ManagementMetricsExporter()
        middleware = MetricsMiddleware(exporter)
        
        stats = middleware.get_stats()
        
        assert "total_requests" in stats
        assert "total_errors" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])