"""
aiplat.stdio — stdio JSON-RPC 持久内核客户端（P1，对接 P0-a StdioKernel）。

封装 `python -m core.acp.stdio_server` 的 JSON-RPC over stdio 协议：
spawn 内核子进程，通过 stdin/stdout JSONL 驱动 Thread（会话）：

    client = StdioKernelClient()
    await client.start()
    thread = await client.thread_start(project_id="p1", requirement="build auth")
    events = await client.thread_events(thread["thread_id"])
    await client.thread_approve(thread["thread_id"], thread["state"], feedback="ok")
    await client.close()

对齐 Codex SDK 的"程序化启停 Thread + 流式监听事件"（Codex-Harness 借鉴 P1，G17）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger("aiplat.stdio")

# 内核启动方式（默认经 python -m；AIPLAT_STDIO_PYTHON 可覆盖解释器）
KERNEL_MODULE = "core.acp.stdio_server"
DEFAULT_KERNEL_CMD = [sys.executable, "-m", KERNEL_MODULE]
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 单行响应上限 10MB


class StdioKernelError(RuntimeError):
    """内核协议错误（含 JSON-RPC error 信封）。"""


class StdioKernelClient:
    """JSON-RPC over stdio 持久内核客户端。

    管理内核子进程生命周期：start() spawn → 请求/响应 → close() 终止。
    """

    def __init__(
        self,
        *,
        kernel_cmd: Optional[list] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        request_timeout: float = 60.0,
    ):
        self._cmd = kernel_cmd or list(DEFAULT_KERNEL_CMD)
        self._cwd = cwd or self._default_cwd()
        self._env = env
        self._timeout = request_timeout
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._transport: Any = None   # 可注入传输（测试用）；None → subprocess stdio
        self._next_id = 1
        self._capabilities: Optional[Dict[str, Any]] = None

    @staticmethod
    def _default_cwd() -> str:
        # 默认在 aiPlat-core 下运行内核模块
        here = os.path.dirname(os.path.abspath(__file__))
        # aiplat-sdk/aiplat → 向上找 aiPlat-core
        for _ in range(6):
            candidate = os.path.join(here, "aiPlat-core")
            if os.path.isdir(candidate):
                return candidate
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
        return os.getcwd()

    # ── 生命周期 ──────────────────────────────────────────────

    async def start(self) -> Dict[str, Any]:
        """spawn 内核进程并初始化。返回 capabilities。"""
        if self._proc is not None:
            return self._capabilities or {}
        if self._transport is not None:
            await self._transport.start()
            self._proc = object()  # 标记已启动（传输注入模式）
        else:
            self._proc = await asyncio.create_subprocess_exec(
                *self._cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        self._capabilities = await self._request("initialize", {})
        return self._capabilities

    async def close(self) -> None:
        """发送 shutdown 并终止子进程。"""
        if self._proc is None:
            return
        try:
            await self._request("shutdown", {})
        except Exception:  # noqa: BLE001 — 关闭阶段 best-effort
            logger.debug("shutdown failed", exc_info=True)
        if self._transport is not None:
            await self._transport.close()
            self._transport = None
        elif self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def __aenter__(self) -> "StdioKernelClient":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── Thread 原语 ───────────────────────────────────────────

    async def thread_start(self, project_id: str, requirement: str, prd_data: Any = None) -> Dict[str, Any]:
        """启动 Thread（会话）→ {thread_id, state, run_id}。"""
        return await self._request("thread/start", {
            "project_id": project_id, "requirement": requirement, "prd_data": prd_data,
        })

    async def thread_status(self, thread_id: str) -> Dict[str, Any]:
        return await self._request("thread/status", {"thread_id": thread_id})

    async def thread_events(self, thread_id: str, after_seq: int = 0) -> Dict[str, Any]:
        """拉取 run_events 事件流（item.event 后端）。"""
        return await self._request("thread/events", {"thread_id": thread_id, "after_seq": after_seq})

    async def thread_resume(self, thread_id: str, feedback: str = "") -> Dict[str, Any]:
        return await self._request("thread/resume", {"thread_id": thread_id, "feedback": feedback})

    async def thread_approve(self, thread_id: str, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL allow：批准审批请求并继续。"""
        return await self._request("thread/approve", {"thread_id": thread_id, "state": state, "feedback": feedback})

    async def thread_reject(self, thread_id: str, state: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """HITL deny：拒绝并带反馈继续。"""
        return await self._request("thread/reject", {"thread_id": thread_id, "state": state, "feedback": feedback})

    async def thread_rollback(self, thread_id: str, stage_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("thread/rollback", {"thread_id": thread_id, "stage_id": stage_id, "state": state})

    async def thread_cancel(self, thread_id: str) -> Dict[str, Any]:
        return await self._request("thread/cancel", {"thread_id": thread_id})

    # ── 事件流（流式监听）──────────────────────────────────────

    async def stream_events(self, thread_id: str, poll_interval: float = 0.5) -> AsyncGenerator[Dict[str, Any], None]:
        """持续拉取 thread/events 直到无新事件（轮询式流式监听）。"""
        after_seq = 0
        while True:
            resp = await self.thread_events(thread_id, after_seq=after_seq)
            events = resp.get("events", [])
            for ev in events:
                after_seq = int(ev.get("seq", after_seq))
                yield ev
            if not events:
                break
            await asyncio.sleep(poll_interval)

    # ── 内部 ──────────────────────────────────────────────────

    async def _request(self, method: str, params: Dict[str, Any]) -> Any:
        if self._proc is None:
            raise StdioKernelError("kernel not started — call start() first")
        if self._transport is not None:
            # 注入传输模式（测试/自定义后端）：transport 返回完整 result 或抛错
            result = await self._transport.request(method, params)
            return result
        if self._proc.stdin is None or self._proc.stdout is None:
            raise StdioKernelError("kernel stdin/stdout unavailable")
        req_id = self._next_id
        self._next_id += 1
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
                             ensure_ascii=False)
        try:
            self._proc.stdin.write((payload + "\n").encode("utf-8"))
            await self._proc.stdin.drain()
            raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=self._timeout)
        except asyncio.TimeoutError:
            raise StdioKernelError(f"request timed out: {method}") from None
        if not raw:
            raise StdioKernelError("kernel closed stdin (EOF)")
        resp = json.loads(raw.decode("utf-8"))
        if "error" in resp:
            err = resp["error"]
            raise StdioKernelError(f"{method} failed ({err.get('code')}): {err.get('message')}")
        return resp.get("result")
