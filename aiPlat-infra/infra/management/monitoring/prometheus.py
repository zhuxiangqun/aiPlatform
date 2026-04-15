"""
Prometheus Metrics Exporter for Management Module

Provides metrics export capability for Prometheus monitoring.
"""

from typing import Dict, List, Optional
from datetime import datetime
import time


class PrometheusMetric:
    """Represents a Prometheus metric"""
    
    def __init__(
        self,
        name: str,
        metric_type: str = "gauge",
        help_text: str = "",
        labels: Optional[Dict[str, str]] = None
    ):
        """
        Initialize Prometheus metric.
        
        Args:
            name: Metric name
            metric_type: Type (gauge, counter, histogram, summary)
            help_text: Help description
            labels: Label key-value pairs
        """
        self.name = name
        self.metric_type = metric_type
        self.help_text = help_text
        self.labels = labels or {}
        self.value = 0.0
        self.timestamp = time.time()
    
    def set_value(self, value: float):
        """Set metric value"""
        self.value = value
        self.timestamp = time.time()
    
    def to_prometheus_format(self) -> str:
        """
        Convert to Prometheus text format.
        
        Returns:
            Prometheus formatted string
        """
        lines = []
        
        if self.help_text:
            lines.append(f"# HELP {self.name} {self.help_text}")
        
        lines.append(f"# TYPE {self.name} {self.metric_type}")
        
        if self.labels:
            label_str = ",".join([f'{k}="{v}"' for k, v in self.labels.items()])
            lines.append(f"{self.name}{{{label_str}}} {self.value}")
        else:
            lines.append(f"{self.name} {self.value}")
        
        return "\n".join(lines)


class PrometheusCollector:
    """
    Prometheus metrics collector.
    
    Collects and formats metrics from management modules for Prometheus scraping.
    """
    
    def __init__(self, namespace: str = "aiplat"):
        """
        Initialize collector.
        
        Args:
            namespace: Metric namespace prefix
        """
        self.namespace = namespace
        self._metrics: Dict[str, PrometheusMetric] = {}
    
    def _get_full_name(self, name: str) -> str:
        """Get full metric name with namespace"""
        return f"{self.namespace}_{name}"
    
    def register_metric(
        self,
        name: str,
        metric_type: str = "gauge",
        help_text: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> PrometheusMetric:
        """
        Register a new metric.
        
        Args:
            name: Metric name
            metric_type: Type (gauge, counter, histogram, summary)
            help_text: Help description
            labels: Label key-value pairs
        
        Returns:
            PrometheusMetric instance
        """
        full_name = self._get_full_name(name)
        metric = PrometheusMetric(
            name=full_name,
            metric_type=metric_type,
            help_text=help_text,
            labels=labels
        )
        self._metrics[full_name] = metric
        return metric
    
    def update_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """
        Update a metric value.
        
        Args:
            name: Metric name
            value: Metric value
            labels: Optional labels to update
        """
        full_name = self._get_full_name(name)
        
        if full_name not in self._metrics:
            self.register_metric(name, labels=labels)
        
        metric = self._metrics[full_name]
        if labels:
            metric.labels = labels
        metric.set_value(value)
    
    def get_metric(self, name: str) -> Optional[PrometheusMetric]:
        """
        Get a registered metric.
        
        Args:
            name: Metric name
        
        Returns:
            PrometheusMetric or None
        """
        full_name = self._get_full_name(name)
        return self._metrics.get(full_name)
    
    def collect(self) -> str:
        """
        Collect all metrics in Prometheus format.
        
        Returns:
            Prometheus formatted string
        """
        output = []
        
        for metric in self._metrics.values():
            output.append(metric.to_prometheus_format())
        
        return "\n\n".join(output)
    
    def clear(self):
        """Clear all metrics"""
        self._metrics.clear()


class ManagementMetricsExporter:
    """
    Metrics exporter for management modules.
    
    Provides Prometheus-compatible metric export from management modules.
    """
    
    def __init__(self, namespace: str = "aiplat_infra"):
        """
        Initialize exporter.
        
        Args:
            namespace: Metric namespace prefix
        """
        self.collector = PrometheusCollector(namespace)
        self._setup_default_metrics()
    
    def _setup_default_metrics(self):
        """Setup default management metrics"""
        self.collector.register_metric(
            "manager_status",
            metric_type="gauge",
            help_text="Status of management module (0=unknown, 1=active, 2=inactive, 3=error)"
        )
        
        self.collector.register_metric(
            "manager_health",
            metric_type="gauge",
            help_text="Health status of management module (0=unhealthy, 1=healthy)"
        )
        
        self.collector.register_metric(
            "manager_operations_total",
            metric_type="counter",
            help_text="Total number of operations performed by management module"
        )
        
        self.collector.register_metric(
            "manager_errors_total",
            metric_type="counter",
            help_text="Total number of errors in management module"
        )
    
    async def export_from_manager(self, manager_name: str, manager) -> Dict[str, str]:
        """
        Export metrics from a management manager.
        
        Args:
            manager_name: Manager name
            manager: ManagementBase instance
        
        Returns:
            Dict of metric name to value
        """
        metrics_data = {}
        
        try:
            status = await manager.get_status()
            status_value = {
                "unknown": 0,
                "active": 1,
                "inactive": 2,
                "error": 3,
                "healthy": 1,
                "unhealthy": 0
            }.get(status.value.lower(), 0)
            
            self.collector.update_metric(
                "manager_status",
                float(status_value),
                labels={"manager": manager_name}
            )
            metrics_data["status"] = str(status_value)
        except Exception:
            pass
        
        try:
            health = await manager.health_check()
            health_value = 1.0 if health.status.value.lower() == "healthy" else 0.0
            
            self.collector.update_metric(
                "manager_health",
                health_value,
                labels={"manager": manager_name}
            )
            metrics_data["health"] = str(health_value)
        except Exception:
            pass
        
        try:
            metrics = await manager.get_metrics()
            for metric in metrics:
                labels = metric.labels.copy() if metric.labels else {}
                labels["manager"] = manager_name
                
                self.collector.update_metric(
                    metric.name,
                    metric.value,
                    labels=labels
                )
                metrics_data[metric.name] = str(metric.value)
        except Exception:
            pass
        
        return metrics_data
    
    async def export_from_infra_manager(self, infra_manager) -> str:
        """
        Export metrics from all managers in InfraManager.
        
        Args:
            infra_manager: InfraManager instance
        
        Returns:
            Prometheus formatted metrics string
        """
        self.collector.clear()
        self._setup_default_metrics()
        
        for manager_name in infra_manager.list_managers():
            manager = infra_manager.get(manager_name)
            if manager:
                await self.export_from_manager(manager_name, manager)
        
        return self.collector.collect()
    
    def get_prometheus_output(self) -> str:
        """
        Get collected metrics in Prometheus format.
        
        Returns:
            Prometheus formatted string
        """
        return self.collector.collect()


class MetricsMiddleware:
    """
    Middleware for automatically collecting metrics.
    
    Can be used with FastAPI or other web frameworks.
    """
    
    def __init__(self, exporter: ManagementMetricsExporter):
        """
        Initialize middleware.
        
        Args:
            exporter: ManagementMetricsExporter instance
        """
        self.exporter = exporter
        self._request_count = 0
        self._error_count = 0
    
    async def track_request(self, manager_name: str, operation: str):
        """
        Track a request operation.
        
        Args:
            manager_name: Manager performing the operation
            operation: Operation name
        """
        self._request_count += 1
        
        self.exporter.collector.update_metric(
            "manager_operations_total",
            float(self._request_count),
            labels={"manager": manager_name, "operation": operation}
        )
    
    async def track_error(self, manager_name: str, error_type: str):
        """
        Track an error.
        
        Args:
            manager_name: Manager where error occurred
            error_type: Error type
        """
        self._error_count += 1
        
        self.exporter.collector.update_metric(
            "manager_errors_total",
            float(self._error_count),
            labels={"manager": manager_name, "error_type": error_type}
        )
    
    def get_stats(self) -> Dict[str, int]:
        """Get middleware statistics"""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count
        }