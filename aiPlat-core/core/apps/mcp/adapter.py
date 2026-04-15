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
    """Adapter that wraps an MCP tool as a local ITool"""
    
    def __init__(
        self,
        mcp_tool: MCPTool,
        client: MCPClient,
        timeout: int = 30000
    ):
        self._mcp_tool = mcp_tool
        self._client = client
        self._timeout = timeout
        
        # Create ToolConfig from MCP tool
        config = ToolConfig(
            name=f"mcp_{mcp_tool.name}",
            description=mcp_tool.description,
            parameters=mcp_tool.input_schema
        )
        super().__init__(config)
        
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the MCP tool via client"""
        start_time = asyncio.get_event_loop().time()
        
        try:
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
        registry: "ToolRegistry"
    ) -> int:
        """
        Register all tools from an MCP server to the local registry.
        Returns the number of tools registered.
        """
        client = self._manager.get_client(server_name)
        if not client:
            raise ValueError(f"MCP server '{server_name}' not found")
            
        count = 0
        for tool_name, mcp_tool in client.tools.items():
            adapter = MCPToolAdapter(mcp_tool, client)
            registry.register(adapter)
            count += 1
            
        return count


# Type alias for circular import
from ..tools.base import ToolRegistry