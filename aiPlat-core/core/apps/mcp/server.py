"""
MCP Server

Exposes local tools via MCP protocol.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
try:
    import sse_starlette  # type: ignore
except Exception:  # pragma: no cover
    # Optional dependency: keep core importable even if SSE helper is missing.
    sse_starlette = None  # type: ignore

from core.harness.syscalls.tool import sys_tool_call

from .types import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerCapabilities,
    MCPTool,
    MCPResource,
    TransportType,
)
from .protocol import MCPProtocolHandler

logger = logging.getLogger(__name__)


@dataclass
class MCPServerState:
    """MCP Server state"""
    capabilities: MCPServerCapabilities
    protocol_version: str = "2024-11-05"
    server_info: Dict[str, str] = None
    
    def __post_init__(self):
        if self.server_info is None:
            self.server_info = {
                "name": "aiplat-core-mcp",
                "version": "1.0.0"
            }


class MCPServer:
    """MCP Server - exposes local tools via MCP protocol"""
    
    def __init__(
        self,
        tools: Dict[str, Any],
        resources: Optional[Dict[str, Any]] = None
    ):
        self._tools = tools
        self._resources = resources or {}
        self._protocol = MCPProtocolHandler()
        self._state = MCPServerCapabilities(tools=True, resources=True)
        
    @property
    def app(self) -> FastAPI:
        """Get FastAPI app for the server"""
        app = FastAPI(title="aiPlat-core MCP Server")
        
        @app.get("/mcp")
        async def mcp_sse(request: Request):
            """SSE endpoint for MCP protocol"""
            return StreamingResponse(
                self._handle_sse(request),
                media_type="text/event-stream"
            )
            
        @app.post("/mcp")
        async def mcp_jsonrpc(request: Request):
            """JSON-RPC endpoint for MCP protocol"""
            body = await request.body()
            return await self._handle_jsonrpc(body)
            
        @app.get("/mcp/tools")
        async def list_tools():
            """List available tools"""
            return {
                "tools": [
                    {
                        "name": name,
                        "description": tool.get_description(),
                        "inputSchema": tool.get_schema().parameters
                    }
                    for name, tool in self._tools.items()
                ]
            }
            
        @app.get("/mcp/resources")
        async def list_resources():
            """List available resources"""
            return {
                "resources": [
                    {
                        "uri": uri,
                        "name": res.get("name", uri),
                        "description": res.get("description"),
                        "mimeType": res.get("mimeType")
                    }
                    for uri, res in self._resources.items()
                ]
            }
            
        @app.get("/health")
        async def health():
            """Health check"""
            return {"status": "healthy", "tools": len(self._tools)}
            
        return app
        
    async def _handle_sse(self, request: Request):
        """Handle SSE connection"""
        def _event(data: str) -> Any:
            # Prefer sse-starlette event helper when available; otherwise emit raw SSE lines.
            if sse_starlette is not None:
                return sse_starlette.SSEEvent(data=data)
            return f"data: {data}\n\n"

        def _comment(line: str) -> Any:
            if sse_starlette is not None:
                return sse_starlette.SSEEvent(data=f": {line}")
            return f": {line}\n\n"

        async def event_generator():
            # Send initialize response
            yield _event(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "result": {
                            "protocolVersion": self._state.protocol_version,
                            "capabilities": {"tools": True, "resources": True},
                            "serverInfo": self._state.server_info,
                        },
                    }
                )
            )
            
            # Keep connection alive
            while True:
                await asyncio.sleep(5)
                yield _comment("keepalive")
                
        return event_generator()
        
    async def _handle_jsonrpc(self, body: bytes) -> Response:
        """Handle JSON-RPC request"""
        try:
            json_data = json.loads(body.decode("utf-8"))
            request = JSONRPCRequest.from_dict(json_data)
            
            # Route to handler
            if request.method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": True,
                        "resources": True
                    },
                    "serverInfo": {
                        "name": "aiplat-core-mcp",
                        "version": "1.0.0"
                    }
                }
                
            elif request.method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": name,
                            "description": tool.get_description(),
                            "inputSchema": tool.get_schema().parameters
                        }
                        for name, tool in self._tools.items()
                    ]
                }
                
            elif request.method == "tools/call":
                tool_name = request.params.get("name")
                arguments = request.params.get("arguments", {})
                
                if tool_name not in self._tools:
                    return Response(
                        content=json.dumps({
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "error": {
                                "code": -32601,
                                "message": f"Tool '{tool_name}' not found"
                            }
                        }),
                        media_type="application/json"
                    )
                    
                tool = self._tools[tool_name]
                
                # Execute tool
                try:
                    # Assume tool has execute method
                    if hasattr(tool, 'execute'):
                        result_obj = await sys_tool_call(
                            tool,
                            arguments if isinstance(arguments, dict) else {},
                            user_id="system",
                            session_id="mcp",
                        )
                        result = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(getattr(result_obj, "output", None) or getattr(result_obj, "error", None) or result_obj)
                                }
                            ]
                        }
                    else:
                        result = {"content": [{"type": "text", "text": "Tool not executable"}]}
                except Exception as e:
                    return Response(
                        content=json.dumps({
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "error": {
                                "code": -32603,
                                "message": str(e)
                            }
                        }),
                        media_type="application/json"
                    )
                    
            elif request.method == "resources/list":
                result = {
                    "resources": [
                        {
                            "uri": uri,
                            "name": res.get("name", uri),
                            "description": res.get("description"),
                            "mimeType": res.get("mimeType")
                        }
                        for uri, res in self._resources.items()
                    ]
                }
                
            else:
                return Response(
                    content=json.dumps({
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{request.method}' not found"
                        }
                    }),
                    media_type="application/json"
                )
                
            # Send success response
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "result": result
                }),
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error(f"MCP JSON-RPC error: {e}")
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }),
                media_type="application/json",
                status_code=500
            )


def create_mcp_server(tools: Dict[str, Any]) -> FastAPI:
    """Create MCP server FastAPI app"""
    server = MCPServer(tools)
    return server.app
