"""
MCP Tool Adapter

Converts MCP Tools to local ITool interface for integration with the tool system.
"""

import asyncio
from typing import Any, Dict, Optional

from ...harness.interfaces import ITool, ToolConfig, ToolSchema, ToolResult
from ..tools.base import BaseTool
from .client import MCPClient, MCPClientManager
from .types import MCPTool


class MCPToolAdapter(BaseTool):
    """
    Adapter that wraps an MCP tool as a local ToolRegistry tool.

    - Tool name is namespaced by server to avoid collisions:
        mcp.<server_name>.<tool_name>
    - risk_level / approval hints are conveyed via ToolConfig.metadata, consumed by PolicyGate.
    """
    
    def __init__(
        self,
        mcp_tool: MCPTool,
        client: MCPClient,
        timeout: int = 30000,
        *,
        server_name: str,
        tool_name: str,
        risk_level: str = "medium",
        approval_required: bool = False,
        disabled_reason: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        self._mcp_tool = mcp_tool
        self._client = client
        self._timeout = timeout
        self._disabled_reason = disabled_reason
        
        # Create ToolConfig from MCP tool
        metadata = {
            "category": "mcp",
            "mcp_server": server_name,
            "mcp_tool": tool_name,
            "risk_level": risk_level,
            # When true, PolicyGate will request approval even if global syscall approval is off.
            "approval_required": bool(approval_required),
        }
        if disabled_reason:
            metadata["disabled_reason"] = disabled_reason
        if extra_metadata:
            try:
                metadata.update(extra_metadata)
            except Exception:
                pass
        config = ToolConfig(
            name=f"mcp.{server_name}.{tool_name}",
            description=mcp_tool.description,
            parameters=mcp_tool.input_schema,
            metadata=metadata,
        )
        super().__init__(config)
        
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the MCP tool via client"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if self._disabled_reason:
                latency = asyncio.get_event_loop().time() - start_time
                return ToolResult(
                    success=False,
                    error=f"policy_denied: {self._disabled_reason}",
                    latency=latency,
                    metadata={"code": "POLICY_DENIED", "reason": self._disabled_reason},
                )

            result = await asyncio.wait_for(
                self._client.call_tool(self._mcp_tool.name, params),
                timeout=self._timeout / 1000
            )
            
            latency = asyncio.get_event_loop().time() - start_time
            
            if result.is_error:
                return ToolResult(
                    success=False,
                    error=result.content,
                    latency=latency
                )
                
            return ToolResult(
                success=True,
                output=result.content,
                latency=latency
            )
            
        except asyncio.TimeoutError:
            latency = asyncio.get_event_loop().time() - start_time
            return ToolResult(
                success=False,
                error=f"Tool execution timed out after {self._timeout}ms",
                latency=latency
            )
        except Exception as e:
            latency = asyncio.get_event_loop().time() - start_time
            return ToolResult(
                success=False,
                error=str(e),
                latency=latency
            )


class MCPToolExporter:
    """Exports local ITool as MCP tool (for server mode)"""
    
    @staticmethod
    def to_mcp_tool(tool: ITool) -> MCPTool:
        """Convert local ITool to MCP Tool"""
        schema = tool.get_schema()
        
        return MCPTool(
            name=tool.get_name(),
            description=tool.get_description(),
            input_schema={
                "type": "object",
                "properties": schema.parameters.get("properties", {}),
                "required": schema.parameters.get("required", [])
            }
        )


class MCPClientWrapper:
    """Wrapper for integrating MCP clients with ToolRegistry"""
    
    def __init__(self, manager: MCPClientManager):
        self._manager = manager
        
    async def register_server_tools(
        self,
        server_name: str,
        registry: "ToolRegistry",
        *,
        allowed_tools: Optional[list] = None,
        risk_level: str = "medium",
        tool_risk: Optional[Dict[str, str]] = None,
        approval_required: Optional[bool] = None,
        disabled_reason: Optional[str] = None,
    ) -> int:
        """
        Register all tools from an MCP server to the local registry.
        Returns the number of tools registered.
        """
        client = self._manager.get_client(server_name)
        if not client:
            raise ValueError(f"MCP server '{server_name}' not found")
            
        allow = set([str(x) for x in (allowed_tools or []) if str(x).strip()])
        tool_risk = tool_risk or {}
        count = 0
        for tool_name, mcp_tool in client.tools.items():
            if allow and tool_name not in allow:
                continue
            r = str(tool_risk.get(tool_name) or risk_level or "medium")
            need_approval = bool(approval_required) if approval_required is not None else (r in {"high", "critical"})
            adapter = MCPToolAdapter(
                mcp_tool,
                client,
                server_name=server_name,
                tool_name=tool_name,
                risk_level=r,
                approval_required=need_approval,
                disabled_reason=disabled_reason,
            )
            registry.register(adapter)
            count += 1
            
        return count


# Type alias for circular import
from ..tools.base import ToolRegistry
