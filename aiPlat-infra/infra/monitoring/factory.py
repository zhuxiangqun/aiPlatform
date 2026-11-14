"""factory：模块接口。"""

from typing import Optional
from .schemas import MonitoringConfig
from .base import MetricsCollector, HealthChecker, AlertManager
from .collector import (
    PrometheusMetricsCollector,
    SimpleHealthChecker,
    SimpleAlertManager,
)


def create_monitoring_system(config: Optional[MonitoringConfig] = None) -> dict:
    """创建 monitoring_system。

    Args:
        config: config 参数。
    """
    config = config or MonitoringConfig()

    return {
        "metrics": PrometheusMetricsCollector(config),
        "health": SimpleHealthChecker(config),
        "alerts": SimpleAlertManager(config),
    }


def create_metrics_collector(
    config: Optional[MonitoringConfig] = None,
) -> MetricsCollector:
    """创建 metrics_collector。

    Args:
        config: config 参数。
    """
    config = config or MonitoringConfig()
    return PrometheusMetricsCollector(config)


def create_health_checker(config: Optional[MonitoringConfig] = None) -> HealthChecker:
    """创建 health_checker。

    Args:
        config: config 参数。
    """
    config = config or MonitoringConfig()
    return SimpleHealthChecker(config)


def create_alert_manager(config: Optional[MonitoringConfig] = None) -> AlertManager:
    """创建 alert_manager。

    Args:
        config: config 参数。
    """
    config = config or MonitoringConfig()
    return SimpleAlertManager(config)
