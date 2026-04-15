"""
Monitoring Manager

Manages system monitoring and alerting.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import AlertRule, Alert
from datetime import datetime
import time


class MonitoringManager(ManagementBase):
    """
    Manager for system monitoring and alerting.
    
    Provides alerting, threshold management, and health monitoring.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._alert_rules: Dict[str, AlertRule] = {}
        self._alerts: List[Alert] = []
        self._alert_history: List[Dict] = []
        self._thresholds: Dict[str, float] = {}
    
    async def get_status(self) -> Status:
        """Get monitoring module status."""
        try:
            active_alerts = [a for a in self._alerts if a.status == "active"]
            
            if not active_alerts:
                return Status.HEALTHY
            elif len(active_alerts) < 3:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get monitoring metrics."""
        metrics = []
        timestamp = time.time()
        
        # Alert metrics
        metrics.append(Metrics(
            name="monitoring.alerts_total",
            value=len(self._alerts),
            unit="count",
            timestamp=timestamp,
            labels={"module": "monitoring"}
        ))
        
        active_alerts = [a for a in self._alerts if a.status == "active"]
        metrics.append(Metrics(
            name="monitoring.alerts_active",
            value=len(active_alerts),
            unit="count",
            timestamp=timestamp,
            labels={"module": "monitoring"}
        ))
        
        # Alert rules
        metrics.append(Metrics(
            name="monitoring.rules_total",
            value=len(self._alert_rules),
            unit="count",
            timestamp=timestamp,
            labels={"module": "monitoring"}
        ))
        
        enabled_rules = [r for r in self._alert_rules.values() if r.enabled]
        metrics.append(Metrics(
            name="monitoring.rules_enabled",
            value=len(enabled_rules),
            unit="count",
            timestamp=timestamp,
            labels={"module": "monitoring"}
        ))
        
        # Alert by severity
        severities = {"critical": 0, "warning": 0, "info": 0}
        for alert in self._alerts:
            if alert.status == "active":
                rule = self._alert_rules.get(alert.rule_name)
                if rule:
                    severities[rule.severity] += 1
        
        for severity, count in severities.items():
            metrics.append(Metrics(
                name=f"monitoring.alerts_by_severity",
                value=count,
                unit="count",
                timestamp=timestamp,
                labels={"module": "monitoring", "severity": severity}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform monitoring health check."""
        try:
            status = await self.get_status()
            
            active_alerts = [a for a in self._alerts if a.status == "active"]
            severity_count = {"critical": 0, "warning": 0, "info": 0}
            
            for alert in active_alerts:
                rule = self._alert_rules.get(alert.rule_name)
                if rule:
                    severity_count[rule.severity] += 1
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="No active alerts",
                    details={
                        "total_alerts": len(self._alerts),
                        "active_alerts": 0,
                        "rules": len(self._alert_rules)
                    }
                )
            elif status == Status.DEGRADED:
                return HealthStatus(
                    status=status,
                    message=f"Minor alerts active",
                    details={
                        "active_alerts": len(active_alerts),
                        "by_severity": severity_count
                    }
                )
            else:
                return HealthStatus(
                    status=status,
                    message=f"Critical alerts active: {len(active_alerts)}",
                    details={
                        "active_alerts": len(active_alerts),
                        "by_severity": severity_count
                    }
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    # Monitoring-specific methods
    
    async def add_alert_rule(self, rule: AlertRule) -> bool:
        """
        Add an alert rule.
        
        Args:
            rule: Alert rule configuration
        
        Returns:
            True if added successfully
        """
        self._alert_rules[rule.name] = rule
        return True
    
    async def remove_alert_rule(self, name: str) -> bool:
        """
        Remove an alert rule.
        
        Args:
            name: Rule name
        
        Returns:
            True if removed
        """
        if name in self._alert_rules:
            del self._alert_rules[name]
            return True
        return False
    
    async def get_alert_rules(self) -> List[AlertRule]:
        """
        Get all alert rules.
        
        Returns:
            List of alert rules
        """
        return list(self._alert_rules.values())
    
    async def enable_rule(self, name: str) -> bool:
        """
        Enable an alert rule.
        
        Args:
            name: Rule name
        
        Returns:
            True if enabled
        """
        if name in self._alert_rules:
            self._alert_rules[name].enabled = True
            return True
        return False
    
    async def disable_rule(self, name: str) -> bool:
        """
        Disable an alert rule.
        
        Args:
            name: Rule name
        
        Returns:
            True if disabled
        """
        if name in self._alert_rules:
            self._alert_rules[name].enabled = False
            return True
        return False
    
    async def trigger_alert(self, rule_name: str, message: str = None) -> Alert:
        """
        Trigger an alert.
        
        Args:
            rule_name: Rule name
            message: Alert message
        
        Returns:
            Created alert
        """
        rule = self._alert_rules.get(rule_name)
        if not rule or not rule.enabled:
            return None
        
        alert_id = f"alert-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self._alerts)}"
        
        alert = Alert(
            alert_id=alert_id,
            rule_name=rule_name,
            status="active",
            message=message or f"Alert triggered for {rule_name}",
            started_at=datetime.now()
        )
        
        self._alerts.append(alert)
        
        self._alert_history.append({
            "alert_id": alert_id,
            "action": "triggered",
            "timestamp": datetime.now().isoformat(),
            "rule_name": rule_name,
            "severity": rule.severity
        })
        
        return alert
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """
        Resolve an alert.
        
        Args:
            alert_id: Alert ID
        
        Returns:
            True if resolved
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.status = "resolved"
                alert.resolved_at = datetime.now()
                
                self._alert_history.append({
                    "alert_id": alert_id,
                    "action": "resolved",
                    "timestamp": datetime.now().isoformat(),
                    "rule_name": alert.rule_name
                })
                
                return True
        
        return False
    
    async def get_alerts(self, status: str = None, limit: int = 100) -> List[Alert]:
        """
        Get alerts.
        
        Args:
            status: Filter by status (active, resolved)
            limit: Maximum number to return
        
        Returns:
            List of alerts
        """
        alerts = self._alerts
        
        if status:
            alerts = [a for a in alerts if a.status == status]
        
        return sorted(alerts, key=lambda a: a.started_at, reverse=True)[:limit]
    
    async def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """
        Get alert history.
        
        Args:
            limit: Maximum number to return
        
        Returns:
            List of alert history entries
        """
        return self._alert_history[-limit:]
    
    async def set_threshold(self, metric_name: str, threshold: float) -> None:
        """
        Set a metric threshold.
        
        Args:
            metric_name: Metric name
            threshold: Threshold value
        """
        self._thresholds[metric_name] = threshold
    
    async def get_threshold(self, metric_name: str) -> Optional[float]:
        """
        Get a metric threshold.
        
        Args:
            metric_name: Metric name
        
        Returns:
            Threshold value or None
        """
        return self._thresholds.get(metric_name)
    
    async def check_thresholds(self, metrics: Dict[str, float]) -> List[Dict]:
        """
        Check metrics against thresholds.
        
        Args:
            metrics: Dict of metric name to value
        
        Returns:
            List of violations
        """
        violations = []
        
        for metric_name, value in metrics.items():
            threshold = self._thresholds.get(metric_name)
            if threshold is not None and value > threshold:
                violations.append({
                    "metric": metric_name,
                    "value": value,
                    "threshold": threshold,
                    "violation": value - threshold
                })
        
        return violations
    
    async def clear_alerts(self) -> int:
        """
        Clear all resolved alerts.
        
        Returns:
            Number of alerts cleared
        """
        original_count = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.status == "active"]
        return original_count - len(self._alerts)
    
    async def get_cluster_metrics(self) -> Dict[str, Any]:
        """
        Get cluster-level metrics.
        
        Returns:
            Dict of cluster metrics
        """
        return {
            "nodes": {
                "total": 0,
                "healthy": 0,
                "unhealthy": 0
            },
            "gpus": {
                "total": 0,
                "available": 0,
                "utilized": 0
            },
            "cpu": {
                "total_cores": 0,
                "utilization": 0.0
            },
            "memory": {
                "total_bytes": 0,
                "utilization": 0.0
            },
            "network": {
                "ingress_throughput": 0.0,
                "egress_throughput": 0.0
            }
        }
    
    async def get_gpu_metrics(self) -> List[Dict[str, Any]]:
        """
        Get GPU metrics for all nodes.
        
        Returns:
            List of GPU metrics
        """
        return []
    
    async def list_alert_rules(self) -> List[Dict[str, Any]]:
        """
        List all alert rules.
        
        Returns:
            List of alert rules
        """
        return [
            {
                "name": rule.name,
                "metric": rule.metric,
                "threshold": rule.threshold,
                "duration": rule.duration,
                "severity": rule.severity,
                "enabled": rule.enabled
            }
            for rule in self._alert_rules.values()
        ]
    
    async def get_audit_logs(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs."""
        return []
    
    async def get_overview(self) -> Dict[str, Any]:
        """Get monitoring overview."""
        return {
            "cluster_health": "healthy",
            "nodes_total": 1,
            "nodes_healthy": 1,
            "services_total": 0,
            "services_healthy": 0,
            "alerts_active": len(self._alerts),
            "alerts_firing": sum(1 for a in self._alerts.values() if a.status == "firing")
        }
    
    async def get_node_metrics(self, node_name: str) -> Dict[str, Any]:
        """Get metrics for a specific node."""
        return {
            "node": node_name,
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "gpu_usage": 0.0,
            "network_in": 0,
            "network_out": 0
        }
    
    async def get_service_metrics(self, service_name: str) -> Dict[str, Any]:
        """Get metrics for a specific service."""
        return {
            "service": service_name,
            "requests_per_second": 0,
            "latency_ms": 0,
            "error_rate": 0.0,
            "cpu_usage": 0.0,
            "memory_usage": 0.0
        }