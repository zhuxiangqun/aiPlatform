import asyncio
import json
from typing import Optional, Dict
from ..base import MCPTransport
from ..schemas import MCPConfig


class StdIOTransport(MCPTransport):
    def __init__(self, config: MCPConfig):
        self.config = config
        self._process = None
        self._reader = None
        self._writer = None

    async def connect(self) -> None:
        if not self.config.server_command:
            raise ValueError("server_command is required for stdio transport")

        self._process = await asyncio.create_subprocess_exec(
            *self.config.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = self._process.stdout
        self._writer = self._process.stdin

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            await self._process.wait()

    async def send(self, method: str, params: dict = None) -> dict:
        if not self._writer:
            raise RuntimeError("Not connected")

        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        self._writer.write((json.dumps(request) + "\n").encode())
        await self._writer.drain()

        line = await self._reader.readline()
        return json.loads(line.decode())


class HTTPTransport(MCPTransport):
    def __init__(self, config: MCPConfig):
        self.config = config
        self._client = None

    async def connect(self) -> None:
        if not self.config.server_url:
            raise ValueError("server_url is required for http transport")

    async def disconnect(self) -> None:
        pass

    async def send(self, method: str, params: dict = None) -> dict:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                },
                timeout=self.config.timeout,
            )
            return response.json()


class WebSocketTransport(MCPTransport):
    def __init__(self, config: MCPConfig):
        self.config = config
        self._ws = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._connected = False
        self._headers: Dict[str, str] = {}

    def set_headers(self, headers: Dict[str, str]) -> None:
        self._headers.update(headers)

    def set_auth_token(self, token: str) -> None:
        self._headers["Authorization"] = f"Bearer {token}"

    async def connect(self) -> None:
        if not self.config.server_url:
            raise ValueError("server_url is required for websocket transport")

        import websockets
        from websockets.exceptions import ConnectionClosed

        try:
            extra_headers = self._headers if self._headers else None
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self.config.server_url,
                    extra_headers=extra_headers,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=self.config.timeout,
                ),
                timeout=self.config.timeout,
            )
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        except asyncio.TimeoutError:
            raise ConnectionError(f"WebSocket connection timeout after {self.config.timeout}s")
        except Exception as e:
            raise ConnectionError(f"WebSocket connection failed: {e}")

    async def _receive_loop(self) -> None:
        import websockets
        while self._connected and self._ws:
            try:
                message = await self._ws.recv()
                response = json.loads(message)
                request_id = response.get("id")
                if request_id is not None and request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(response)
            except websockets.exceptions.ConnectionClosed:
                self._connected = False
                for future in self._pending_requests.values():
                    if not future.done():
                        future.set_exception(ConnectionError("WebSocket connection closed"))
                self._pending_requests.clear()
                break
            except Exception:
                self._connected = False
                break

    async def _heartbeat_loop(self) -> None:
        while self._connected and self._ws:
            try:
                await asyncio.sleep(30)
                if self._connected and self._ws:
                    await self._ws.ping()
            except Exception:
                self._connected = False
                break

    async def send(self, method: str, params: dict = None) -> dict:
        if not self._ws or not self._connected:
            raise RuntimeError("WebSocket not connected")

        self._request_id += 1
        request_id = self._request_id
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws.send(json.dumps(request))
            response = await asyncio.wait_for(future, timeout=self.config.timeout)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"WebSocket request timeout after {self.config.timeout}s")
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise ConnectionError(f"WebSocket send failed: {e}")

    async def disconnect(self) -> None:
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and self._ws.open
