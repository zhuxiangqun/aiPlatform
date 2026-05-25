"""Workbench Module — Web UI (DEPRECATED placeholder)

工作台模块提供可视化的 Web 管理界面。

⚠ DEPRECATED: This module contains placeholder stubs (WorkbenchClient,
MCPServers, PluginMarket) that return descriptive dicts but do NOT
render any real UI. The actual "项目工作台" web UI lives in
aiPlat-management/frontend/ (React app at /app/projects).

These stubs are retained for documentation of the intended interface.
Do NOT wire into production — use management frontend instead.
"""

from .client import workbench_client

__all__ = ["workbench_client"]