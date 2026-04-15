"""
API Module - Management System API

This module provides REST API endpoints for the management system.

Architecture Boundary:
- This layer provides unified API entry point for frontend
- Business logic is delegated to aiPlat-infra and aiPlat-core layers
- Management layer handles: Dashboard, Alerting, Diagnostics
"""

from .dashboard import router as dashboard_router
from .alerting import router as alerting_router, alias_router as alerts_router
from .diagnostics import router as diagnostics_router
from .infra import router as infra_router
from .core import router as core_router

__all__ = [
    "dashboard_router",
    "alerting_router",
    "alerts_router",
    "diagnostics_router",
    "infra_router",
    "core_router",
]