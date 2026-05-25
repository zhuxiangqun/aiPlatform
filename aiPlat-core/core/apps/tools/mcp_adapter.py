"""MCP (Model Context Protocol) adapter — JSON-RPC over stdio.

Enables dynamic tool discovery from MCP-compatible servers.
Implements the minimal protocol subset: initialize, tools/list, tools/call.

Per CLAUDE.md §5.24: MCP is the highest-cost extension mechanism; use when
a full external service integration is needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class McpClient:
    """Lightweight MCP client using JSON-RPC over stdio subprocess."""

    def __init__(self, command: str, args: List[str], cwd: Optional[str] = None):
        self._command = command
        self._args = args
        self._cwd = cwd
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._capabilities: Dict[str, Any] = {}
        self._initialized = False

    async def start(self) -> bool:
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._command, *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            asyncio.create_task(self._read_loop())
            result = await self._call("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aiplat-mcp", "version": "0.1.0"},
            })
            if result and not isinstance(result, Exception):
                self._capabilities = result.get("capabilities", {}) or {}
                self._initialized = True
                await self._notify("notifications/initialized", {})
                logger.info(f"MCP server started: {self._command} {' '.join(self._args)}")
                return True
            return False
        except Exception:
            logger.debug(f"MCP server '{self._command}' failed to start", exc_info=True)
            return False

    async def stop(self) -> None:
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        result = await self._call("tools/list", {})
        if isinstance(result, dict):
            return result.get("tools", [])
        return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        return await self._call("tools/call", {"name": name, "arguments": arguments})

    async def _call(self, method: str, params: Dict[str, Any]) -> Any:
        if not self._process:
            raise RuntimeError("MCP server not started")
        req_id = self._request_id
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        line = json.dumps(request, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise
        finally:
            self._pending.pop(req_id, None)

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        if not self._process:
            return
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                req_id = data.get("id")
                if req_id is not None and req_id in self._pending:
                    if "error" in data:
                        self._pending[req_id].set_exception(
                            RuntimeError(data["error"].get("message", "MCP error")))
                    else:
                        self._pending[req_id].set_result(data.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


class McpAdapter:
    """Adapter that discovers tools from MCP servers and registers them."""

    def __init__(self):
        self._servers: Dict[str, McpClient] = {}

    async def connect_all(self, servers: List[Dict[str, Any]]) -> int:
        """Connect to all configured MCP servers.

        Each server dict should have: name, command, args (optional).
        Returns number of successfully connected servers.
        """
        count = 0
        for srv in servers:
            name = srv.get("name", "unnamed")
            if name in self._servers:
                continue
            client = McpClient(
                command=srv.get("command", ""),
                args=srv.get("args", []),
                cwd=srv.get("cwd"),
            )
            if await client.start():
                self._servers[name] = client
                count += 1
        return count

    async def disconnect_all(self) -> None:
        for client in self._servers.values():
            await client.stop()
        self._servers.clear()

    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Discover all tools from all connected MCP servers.

        Discovered tools are registered into ToolRegistry by the caller
        (server.py:856) via _make_discovery_tool() so agents can call them
        through the standard sys_tool_call → PolicyGate path.
        """
        all_tools: List[Dict[str, Any]] = []
        for name, client in self._servers.items():
            try:
                tools = await client.list_tools()
                for t in tools:
                    tool_def = {
                        "id": f"mcp_{name}_{t.get('name', 'unknown')}",
                        "name": t.get("name", "unknown"),
                        "description": f"[MCP:{name}] {t.get('description', '')}",
                        "parameters": t.get("inputSchema", {}),
                        "server_name": name,
                        "call_type": "mcp",
                        "execute": lambda args=tool_def, c=client: asyncio.get_event_loop().create_task(
                            c.call_tool(args.get("name", ""), args)),
                    }
                    all_tools.append(tool_def)
            except Exception:
                logger.debug(f"MCP server '{name}' failed to list tools", exc_info=True)
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        client = self._servers.get(server_name)
        if client is None:
            raise RuntimeError(f"MCP server '{server_name}' not connected")
        return await client.call_tool(tool_name, arguments)


_mcp_adapter: Optional[McpAdapter] = None


async def get_mcp_adapter() -> McpAdapter:
    global _mcp_adapter
    if _mcp_adapter is None:
        _mcp_adapter = McpAdapter()
        # Auto-connect from MCP_SERVERS env var
        servers_json = os.getenv("AIPLAT_MCP_SERVERS", "")
        if servers_json:
            try:
                servers = json.loads(servers_json)
                await _mcp_adapter.connect_all(servers if isinstance(servers, list) else [])
            except Exception:
                pass
    return _mcp_adapter
