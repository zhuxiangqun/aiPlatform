import asyncio
from typing import List, Optional
from .base import MCPClient
from .schemas import MCPConfig, Tool, ToolResult, Resource, ResourceContent


class MCPClientImpl(MCPClient):
    def __init__(self, config: MCPConfig):
        self.config = config
        self._transport = None
        self._connected = False

    def _get_transport(self):
        if self._transport is None:
            if self.config.type == "stdio":
                from .transport.stdio import StdIOTransport

                self._transport = StdIOTransport(self.config)
            elif self.config.type == "http":
                from .transport.stdio import HTTPTransport

                self._transport = HTTPTransport(self.config)
            elif self.config.type == "websocket":
                from .transport.stdio import WebSocketTransport

                self._transport = WebSocketTransport(self.config)
            else:
                raise ValueError(f"Unknown transport type: {self.config.type}")
        return self._transport

    async def connect(self, server_url: Optional[str] = None) -> None:
        url = server_url or self.config.server_url
        transport = self._get_transport()
        await transport.connect()
        self._connected = True

    async def disconnect(self) -> None:
        if self._transport:
            await self._transport.disconnect()
        self._connected = False

    async def list_tools(self) -> List[Tool]:
        if not self._connected:
            raise RuntimeError("Not connected")
        result = await self._transport.send("tools/list")
        tools = result.get("result", {}).get("tools", [])
        return [Tool(**t) for t in tools]

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        if not self._connected:
            raise RuntimeError("Not connected")
        result = await self._transport.send(
            "tools/call", {"name": name, "arguments": arguments}
        )
        content = result.get("result", {}).get("content", [])
        return ToolResult(content=content, is_error=result.get("error") is not None)

    async def list_resources(self) -> List[Resource]:
        if not self._connected:
            raise RuntimeError("Not connected")
        result = await self._transport.send("resources/list")
        resources = result.get("result", {}).get("resources", [])
        return [Resource(**r) for r in resources]

    async def read_resource(self, uri: str) -> ResourceContent:
        if not self._connected:
            raise RuntimeError("Not connected")
        result = await self._transport.send("resources/read", {"uri": uri})
        contents = result.get("result", {}).get("contents", [])
        if contents:
            return ResourceContent(**contents[0])
        return ResourceContent()

    async def health_check(self) -> bool:
        return self._connected
