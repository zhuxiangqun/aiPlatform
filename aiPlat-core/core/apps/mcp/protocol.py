"""
MCP Protocol Handler

Handles JSON-RPC protocol parsing and message processing for MCP.
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Callable, Optional
import aiohttp

from .types import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerCapabilities,
    MCPInitializeResult,
    MCPTool,
    MCPToolResult,
    MCPResource,
    TransportType,
)


class MCPProtocolHandler:
    """Handles MCP protocol messages"""
    
    def __init__(self):
        self._request_handlers: dict[str, Callable] = {}
        self._notification_handlers: dict[str, Callable] = {}
        
    def register_request_handler(
        self, 
        method: str, 
        handler: Callable[[dict], Any]
    ) -> None:
        """Register a handler for a specific request method"""
        self._request_handlers[method] = handler
        
    def register_notification_handler(
        self, 
        method: str, 
        handler: Callable[[dict], None]
    ) -> None:
        """Register a handler for a specific notification method"""
        self._notification_handlers[method] = handler
        
    async def parse_request(self, data: bytes) -> JSONRPCRequest:
        """Parse incoming JSON-RPC request"""
        try:
            json_data = json.loads(data.decode("utf-8"))
            return JSONRPCRequest.from_dict(json_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON-RPC request: {e}")
            
    async def parse_response(self, data: bytes) -> JSONRPCResponse:
        """Parse incoming JSON-RPC response"""
        try:
            json_data = json.loads(data.decode("utf-8"))
            return JSONRPCResponse.from_dict(json_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON-RPC response: {e}")
            
    def create_request(
        self,
        method: str,
        params: Optional[dict] = None,
        request_id: Optional[int] = None
    ) -> JSONRPCRequest:
        """Create a JSON-RPC request"""
        return JSONRPCRequest(
            method=method,
            params=params,
            id=request_id
        )
        
    def create_response(
        self,
        request_id: Optional[int],
        result: Optional[Any] = None,
        error: Optional[dict] = None
    ) -> JSONRPCResponse:
        """Create a JSON-RPC response"""
        return JSONRPCResponse(
            result=result,
            error=error,
            id=request_id
        )


class SSEHandler:
    """Handles Server-Sent Events transport for MCP"""
    
    def __init__(self, timeout: int = 30000):
        self._timeout = timeout / 1000  # Convert to seconds
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def connect(self, url: str, init_request: JSONRPCRequest) -> AsyncGenerator[bytes, None]:
        """Connect to MCP server via SSE"""
        async with aiohttp.ClientSession() as session:
            self._session = session
            
            # Send initialize request first
            async with session.post(
                url,
                data=init_request.to_json().encode("utf-8"),
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    raise ConnectionError(f"MCP server returned {response.status}")
                    
                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        yield line[6:].encode("utf-8")
                        
    async def call(self, url: str, request: JSONRPCRequest) -> JSONRPCResponse:
        """Send a JSON-RPC request and get response"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=request.to_json().encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as response:
                if response.status != 200:
                    raise ConnectionError(f"MCP server returned {response.status}")
                    
                text = await response.text()
                return await self.parse_response(text.encode("utf-8"))
                
    async def parse_response(self, data: bytes) -> JSONRPCResponse:
        """Parse response data"""
        json_data = json.loads(data.decode("utf-8"))
        return JSONRPCResponse.from_dict(json_data)


class StdioHandler:
    """Handles stdio transport for MCP (local processes)"""
    
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        
    async def spawn(
        self,
        command: str,
        args: list[str],
        cwd: Optional[str] = None
    ) -> None:
        """Spawn a local MCP server process"""
        self._process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
    async def call(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Send a JSON-RPC request via stdio"""
        if not self._process:
            raise RuntimeError("Process not started")
            
        # Send request
        self._process.stdin.write((request.to_json() + "\n").encode())
        await self._process.stdin.drain()
        
        # Read response
        line = await self._process.stdout.readline()
        if not line:
            raise ConnectionError("MCP server closed connection")
            
        return await self.parse_response(line)
        
    async def parse_response(self, data: bytes) -> JSONRPCResponse:
        """Parse response data"""
        json_data = json.loads(data.decode("utf-8"))
        return JSONRPCResponse.from_dict(json_data)
        
    async def close(self) -> None:
        """Close the stdio connection"""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None