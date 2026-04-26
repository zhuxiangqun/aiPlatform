from __future__ import annotations

from typing import Any, Dict, Optional

from core.apps.mcp.runtime import MCPRuntime
from core.apps.tools import get_tool_registry


_RUNTIME: MCPRuntime = MCPRuntime()


def get_mcp_runtime() -> MCPRuntime:
    return _RUNTIME


async def sync_mcp_runtime(*, mcp_manager: Any = None, workspace_mcp_manager: Any = None, tool_registry: Any = None) -> Dict[str, Any]:
    """Best-effort: sync MCP servers into ToolRegistry runtime."""
    try:
        registry = tool_registry or get_tool_registry()
        servers: Dict[str, Any] = {}
        if mcp_manager:
            for s in mcp_manager.list_servers():
                servers[s.name] = s
        if workspace_mcp_manager:
            for s in workspace_mcp_manager.list_servers():
                servers[s.name] = s
        return await _RUNTIME.sync_from_servers(servers=list(servers.values()), tool_registry=registry)
    except Exception:
        return {"connected": [], "skipped": [], "unregistered": []}

