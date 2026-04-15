"""
Management Module for aiPlat-infra

This module provides management interfaces for infrastructure components.
"""

from .base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from .manager import InfraManager
from .schemas import (
    ResourceStats,
    AllocatedResource,
    AlertRule,
    Alert,
    CostBreakdown,
    BudgetStatus,
    NodeInfo,
    SlowQuery,
    CacheStats,
    DBPoolStats,
    GPUStatus,
    ServiceInfo,
    ImageInfo,
    QuotaInfo,
    PolicyInfo,
    TaskInfo,
    AutoscalingPolicy
)

from .node import NodeManager
from .service import ServiceManager
from .scheduler import SchedulerManager

__all__ = [
    "ManagementBase",
    "Status",
    "HealthStatus",
    "Metrics",
    "DiagnosisResult",
    "InfraManager",
    "ResourceStats",
    "AllocatedResource",
    "AlertRule",
    "Alert",
    "CostBreakdown",
    "BudgetStatus",
    "NodeInfo",
    "SlowQuery",
    "CacheStats",
    "DBPoolStats",
    "GPUStatus",
    "ServiceInfo",
    "ImageInfo",
    "QuotaInfo",
    "PolicyInfo",
    "TaskInfo",
    "AutoscalingPolicy",
    "NodeManager",
    "ServiceManager",
    "SchedulerManager",
]