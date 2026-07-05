"""
MCP Client

Connects to external MCP servers and provides tool access.
"""

import asyncio
import logging
import time
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


class MCPCircuitBreaker:
    """Phase 51: Circuit breaker for MCP server fault tolerance.

    Three states: CLOSED (normal) → OPEN (fuse blown) → HALF_OPEN (probing).
    After `failure_threshold` consecutive failures, opens for `recovery_timeout` seconds.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure = 0.0
        self._tripped = False

    @property
    def is_open(self) -> bool:
        if not self._tripped:
            return False
        if time.time() - self._last_failure > self.recovery_timeout:
            self._tripped = False
            self._failures = 0
            logger.info("[mcp] circuit breaker reset (recovery timeout)")
            return False
        return True

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.failure_threshold:
            self._tripped = True
            logger.warning(
                "[mcp] circuit breaker OPEN (%d consecutive failures)", self._failures
            )

    def record_success(self) -> None:
        if self._failures > 0:
            logger.info("[mcp] circuit breaker: failure streak reset")
        self._failures = 0
        self._tripped = False


class MCPClient:
    """MCP Client - connects to external MCP servers"""
    
    def __init__(self, config: MCPClientConfig):
        self._config = config
        self._protocol = MCPProtocolHandler()
        self._transport: Optional[SSEHandler | StdioHandler] = None
        self._connected = False
        self._breaker = MCPCircuitBreaker()  # Phase 51
        self._capabilities: Optional[MCPServerCapabilities] = None
        self._server_info: Dict[str, str] = {}
        self._tools: Dict[str, MCPTool] = {}
        self._request_id = 0
        # P0-1: Lazy loading — only store name+desc on startup, fetch schema on first call
        import os as _os
        self._lazy_load = _os.getenv("AIPLAT_MCP_LAZY_LOAD", "true").lower() not in ("0", "false", "no")
        self._tool_schemas_cached: Dict[str, Dict] = {}  # name → inputSchema (lazy-filled)
        
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
            elif isinstance(self._transport, StdioHandler):
                # For stdio, spawn the subprocess first
                command = self._config.command or ""
                if not command:
                    raise ValueError("stdio transport requires command field")
                args = list(self._config.args or [])
                await self._transport.spawn(command, args)
                response = await self._transport.call("", init_request)
                self._handle_init_response(response)
            else:
                raise ValueError(f"Unsupported transport: {self._config.transport}")
                
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
        if self._lazy_load:
            # Store only name + description; schema loaded on first call
            self._tools = {
                tool["name"]: MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema={}  # Empty — lazy-loaded on first call_tool
                )
                for tool in tools_data
            }
            # Cache full schemas for later lazy fetch
            for tool in tools_data:
                if tool.get("inputSchema"):
                    self._tool_schemas_cached[tool["name"]] = tool["inputSchema"]
        else:
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
        if self._breaker.is_open:
            raise RuntimeError(f"MCP circuit breaker open for '{self._config.server_url}'")
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
            
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
        
        # P0-1: Lazy-load schema on first call if not yet loaded
        if self._lazy_load and not self._tools[name].input_schema:
            schema = self._tool_schemas_cached.get(name)
            if not schema:
                # Fetch from server
                tools_resp = await self._transport.call(
                    self._config.server_url,
                    self._protocol.create_request(
                        method="tools/list", params={},
                        request_id=self._next_id()
                    )
                )
                for t in (tools_resp.result or {}).get("tools", []):
                    if t["name"] == name and t.get("inputSchema"):
                        schema = t["inputSchema"]
                        self._tool_schemas_cached[name] = schema
                        break
            if schema:
                self._tools[name] = MCPTool(
                    name=name,
                    description=self._tools[name].description,
                    input_schema=schema,
                )
            
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
            self._breaker.record_failure()
            return MCPToolResult(
                content=str(response.error),
                is_error=True
            )
            
        # Parse tool result
        content = response.result.get("content", [])
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            self._breaker.record_success()
            return MCPToolResult(content=text, is_error=False)
        
        self._breaker.record_success()
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