"""
Dashboard 模块 - 四层总览和健康状态聚合

负责聚合各层状态，提供统一视图。
"""

from .aggregator import DashboardAggregator
from .infra_adapter import InfraAdapter
from .core_adapter import CoreAdapter
from .platform_adapter import PlatformAdapter
from .app_adapter import AppAdapter

__all__ = [
    "DashboardAggregator",
    "InfraAdapter",
    "CoreAdapter",
    "PlatformAdapter",
    "AppAdapter",
]
