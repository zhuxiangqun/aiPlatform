"""
Dashboard 模块 - 四层总览和健康状态聚合

负责聚合各层状态，提供统一视图。
"""

from .aggregator import DashboardAggregator
from .http_adapter import HttpLayerAdapter, create_default_http_adapter
from .http_adapter import InfraHttpAdapter, CoreHttpAdapter, PlatformHttpAdapter, AppHttpAdapter

# Backward-compatible adapter names (now HTTP-based).
InfraAdapter = InfraHttpAdapter
CoreAdapter = CoreHttpAdapter
PlatformAdapter = PlatformHttpAdapter
AppAdapter = AppHttpAdapter

__all__ = [
    "DashboardAggregator",
    "HttpLayerAdapter",
    "create_default_http_adapter",
    "InfraHttpAdapter",
    "CoreHttpAdapter",
    "PlatformHttpAdapter",
    "AppHttpAdapter",
    "InfraAdapter",
    "CoreAdapter",
    "PlatformAdapter",
    "AppAdapter",
]
