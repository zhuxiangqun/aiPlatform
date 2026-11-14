"""
MCP Protocol Handler

Handles JSON-RPC protocol parsing and message processing for MCP.
"""

import asyncio
import json
import sys
import time
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
        """初始化。
        """
        self._request_handlers: dict[str, Callable] = {}
        self._notification_handlers: dict[str, Callable] = {}
        
    def register_request_handler(
        self, 
        method: str, 
        handler: Callable[[dict], Any]
    ) -> None:
        """Register a handler for a specific request method。

        Args:
            method: method 参数。
            handler: handler 参数。
        """
        self._request_handlers[method] = handler
        
    def register_notification_handler(
        self, 
        method: str, 
        handler: Callable[[dict], None]
    ) -> None:
        """Register a handler for a specific notification method。

        Args:
            method: method 参数。
            handler: handler 参数。
        """
        self._notification_handlers[method] = handler
        
    async def parse_request(self, data: bytes) -> JSONRPCRequest:
        """Parse incoming JSON-RPC request。

        Args:
            data: data 参数。
        """
        try:
            json_data = json.loads(data.decode("utf-8"))
            return JSONRPCRequest.from_dict(json_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON-RPC request: {e}")
            
    async def parse_response(self, data: bytes) -> JSONRPCResponse:
        """Parse incoming JSON-RPC response。

        Args:
            data: data 参数。
        """
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
        """Create a JSON-RPC request。

        Args:
            method: method 参数。
            params: params 参数。
            request_id: request 标识。
        """
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
        """Create a JSON-RPC response。

        Args:
            request_id: request 标识。
            result: result 参数。
            error: error 参数。
        """
        return JSONRPCResponse(
            result=result,
            error=error,
            id=request_id
        )

    def create_sampling_request(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 500,
        model_preferences: Optional[dict] = None,
        request_id: Optional[int] = None,
    ) -> JSONRPCRequest:
        """Phase 53: Create a sampling/createMessage request (MCP Sampling).

        Args:
            messages: messages 参数。
            max_tokens: max_tokens 参数。
            model_preferences: model_preferences 参数。
            request_id: request 标识。
        """
        params = {
            "messages": messages,
            "maxTokens": max_tokens,
        }
        if model_preferences:
            params["modelPreferences"] = model_preferences
        return self.create_request(
            method="sampling/createMessage",
            params=params,
            request_id=request_id or int(time.time() * 1000),
        )


class SSEHandler:
    """Handles Server-Sent Events transport for MCP"""
    
    def __init__(self, timeout: int = 30000):
        """初始化。

        Args:
            timeout: 超时秒数。
        """
        self._timeout = timeout / 1000  # Convert to seconds
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def connect(self, url: str, init_request: JSONRPCRequest) -> AsyncGenerator[bytes, None]:
        """Connect to MCP server via SSE。

        Args:
            url: url 参数。
            init_request: init_request 参数。
        """
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
        """Send a JSON-RPC request and get response。

        Args:
            url: url 参数。
            request: FastAPI Request。
        """
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
        """Parse response data。

        Args:
            data: data 参数。
        """
        json_data = json.loads(data.decode("utf-8"))
        return JSONRPCResponse.from_dict(json_data)


class StdioHandler:
    """Handles stdio transport for MCP (local processes)"""
    
    def __init__(self):
        """初始化。
        """
        self._process: Optional[asyncio.subprocess.Process] = None
        
    async def spawn(
        self,
        command: str,
        args: list[str],
        cwd: Optional[str] = None
    ) -> None:
        """Spawn a local MCP server process.

        Args:
            command: command 参数。
            args: args 参数。
            cwd: cwd 参数。
        """
        resolved = sys.executable if command == "python3" else command
        self._process = await asyncio.create_subprocess_exec(
            resolved,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
    async def call(self, url: str = "", request: JSONRPCRequest = None) -> JSONRPCResponse:
        """Send a JSON-RPC request via stdio (url param ignored, kept for interface compat with SSEHandler).

        Args:
            url: url 参数。
            request: FastAPI Request。
        """
        if request is None:
            raise RuntimeError("No request provided")
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
        """Parse response data。

        Args:
            data: data 参数。
        """
        json_data = json.loads(data.decode("utf-8"))
        return JSONRPCResponse.from_dict(json_data)
        
    async def close(self) -> None:
        """Close the stdio connection"""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None