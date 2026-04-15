"""
MCP Client

Connects to external MCP servers and provides tool access.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .types import (
    MCPTool,
    MCPToolResult,
    MCPClientConfig,
    MCPServerCapabilities,
    MCPInitializeResult,
    TransportType,
)
from .protocol import (
    MCPProtocolHandler,
    SSEHandler,
    StdioHandler,
    JSONRPCRequest,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP Client - connects to external MCP servers"""
    
    def __init__(self, config: MCPClientConfig):
        self._config = config
        self._protocol = MCPProtocolHandler()
        self._transport: Optional[SSEHandler | StdioHandler] = None
        self._connected = False
        self._capabilities: Optional[MCPServerCapabilities] = None
        self._server_info: Dict[str, str] = {}
        self._tools: Dict[str, MCPTool] = {}
        self._request_id = 0
        
    @property
    def is_connected(self) -> bool:
        return self._connected
        
    @property
    def capabilities(self) -> Optional[MCPServerCapabilities]:
        return self._capabilities
        
    @property
    def tools(self) -> Dict[str, MCPTool]:
        return self._tools
        
    async def connect(self) -> None:
        """Connect to MCP server and initialize"""
        if self._connected:
            return
            
        # Create transport handler based on config
        if self._config.transport == TransportType.SSE:
            self._transport = SSEHandler(timeout=self._config.timeout)
        elif self._config.transport == TransportType.STDIO:
            self._transport = StdioHandler()
        else:
            raise ValueError(f"Unsupported transport: {self._config.transport}")
            
        # Create initialize request
        init_request = self._protocol.create_request(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "clientInfo": {
                    "name": "aiplat-core",
                    "version": "1.0.0"
                }
            },
            request_id=0
        )
        
        try:
            if isinstance(self._transport, SSEHandler):
                # For SSE, we need to handle initialization differently
                response = await self._transport.call(
                    self._config.server_url,
                    init_request
                )
                self._handle_init_response(response)
            else:
                # For stdio, spawn process first
                raise NotImplementedError("Stdio transport requires spawn first")
                
            self._connected = True
            logger.info(f"Connected to MCP server at {self._config.server_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise
            
    def _handle_init_response(self, response) -> None:
        """Handle initialize response"""
        if response.is_error:
            raise RuntimeError(f"MCP initialize error: {response.error}")
            
        result = response.result
        if not result:
            raise ValueError("Empty initialize response")
            
        # Parse capabilities
        capabilities_data = result.get("capabilities", {})
        self._capabilities = MCPServerCapabilities(
            tools=capabilities_data.get("tools", False),
            resources=capabilities_data.get("resources", False),
            prompts=capabilities_data.get("prompts", False),
        )
        
        # Parse server info
        server_info = result.get("serverInfo", {})
        self._server_info = {
            "name": server_info.get("name", "unknown"),
            "version": server_info.get("version", "unknown")
        }
        
    async def list_tools(self) -> List[MCPTool]:
        """List available tools from MCP server"""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
            
        request = self._protocol.create_request(
            method="tools/list",
            params={},
            request_id=self._next_id()
        )
        
        response = await self._transport.call(
            self._config.server_url,
            request
        )
        
        if response.is_error:
            raise RuntimeError(f"MCP tools/list error: {response.error}")
            
        tools_data = response.result.get("tools", [])
        self._tools = {
            tool["name"]: MCPTool(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {})
            )
            for tool in tools_data
        }
        
        return list(self._tools.values())
        
    async def call_tool(
        self, 
        name: str, 
        arguments: Optional[Dict[str, Any]] = None
    ) -> MCPToolResult:
        """Call a tool on the MCP server"""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
            
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
            
        request = self._protocol.create_request(
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments or {}
            },
            request_id=self._next_id()
        )
        
        response = await self._transport.call(
            self._config.server_url,
            request
        )
        
        if response.is_error:
            return MCPToolResult(
                content=str(response.error),
                is_error=True
            )
            
        # Parse tool result
        content = response.result.get("content", [])
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            return MCPToolResult(content=text, is_error=False)
            
        return MCPToolResult(content=str(response.result), is_error=False)
        
    async def disconnect(self) -> None:
        """Disconnect from MCP server"""
        if self._transport and isinstance(self._transport, StdioHandler):
            await self._transport.close()
            
        self._connected = False
        self._tools.clear()
        logger.info("Disconnected from MCP server")
        
    def _next_id(self) -> int:
        """Generate next request ID"""
        self._request_id += 1
        return self._request_id


class MCPClientManager:
    """Manages multiple MCP client connections"""
    
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        
    async def add_server(
        self,
        name: str,
        config: MCPClientConfig
    ) -> MCPClient:
        """Add and connect to an MCP server"""
        client = MCPClient(config)
        await client.connect()
        await client.list_tools()
        
        self._clients[name] = client
        logger.info(f"Added MCP server: {name}")
        return client
        
    def get_client(self, name: str) -> Optional[MCPClient]:
        """Get MCP client by name"""
        return self._clients.get(name)
        
    def list_servers(self) -> List[str]:
        """List connected server names"""
        return list(self._clients.keys())
        
    async def remove_server(self, name: str) -> None:
        """Remove an MCP server"""
        if name in self._clients:
            await self._clients[name].disconnect()
            del self._clients[name]
            logger.info(f"Removed MCP server: {name}")