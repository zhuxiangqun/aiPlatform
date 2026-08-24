"""
Stdio JSON-RPC persistent kernel (P0-a, 对标 Codex app-server).

把 aiPlat 内核能力（PipelineSession 生命周期 + run_events 事件流 + HITL 审批）
暴露为 JSON-RPC over stdio 协议——外部程序/CI/SRE 面板可 spawn 本进程，通过
stdin/stdout JSONL 驱动 Thread（会话），断线后按 thread_id resume。

设计依据：docs/research/Codex-Harness开源借鉴分析报告.md §2.1 (P0-a)
参考实现：codex-rs/app-server-transport/src/transport/stdio.rs（JSONL 行协议）

协议方法（JSON-RPC 2.0，每行一个 JSON 消息）：
- thread/start        {project_id, requirement, prd_data?} → {thread_id, state}
- thread/status       {thread_id} → {state, phase}
- thread/events       {thread_id, after_seq?} → {events: [...]}（run_events 流式）
- thread/resume       {thread_id} → {state}（断线恢复）
- thread/approve      {thread_id, state, feedback?} → {state}（HITL allow）
- thread/reject       {thread_id, state, feedback} → {state}（HITL deny）
- thread/rollback     {thread_id, state, stage_id} → {state}
- thread/cancel       {thread_id} → {status}
- initialize          {client_name?} → {protocol_version, capabilities}
- shutdown            {} → {status: "ok"}

事件推送：处理 thread/start|resume|approve|reject 后，主动向 stdout 推送
{"method": "item.event", "params": {...}}（对齐 run_events 事件类型）。

用法：python -m core.acp.stdio_server  （AIPLAT_STDIO_KERNEL=1 可选显式）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger("stdio_kernel")

# JSON-RPC 2.0 常量
JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "0.1.0"
# 背压语义（对齐 codex -32001：过载建议指数退避）
ERR_SERVER_OVERLOADED = -32001
# 最大请求并发（防过载，超出返回 -32001）
MAX_CONCURRENT = 4


class _Counter:
    def __init__(self) -> None:
        self.value = 0

    async def __aenter__(self) -> None:
        self.value += 1

    async def __aexit__(self, *exc: Any) -> None:
        self.value -= 1


class StdioKernel:
    """JSON-RPC over stdio 持久会话内核（单进程单会话池）。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, Any] = {}   # thread_id → PipelineSession
        self._states: Dict[str, Dict[str, Any]] = {}  # thread_id → last state
        self._after_seq: Dict[str, int] = {}  # thread_id → last consumed event seq
        self._concurrent = _Counter()
        self._shutdown = False

    # ── 生命周期 ──────────────────────────────────────────────

    async def initialize(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "jsonrpc": JSONRPC_VERSION,
            "capabilities": {
                "thread": ["start", "status", "events", "resume",
                           "approve", "reject", "rollback", "cancel"],
                "events": ["item.event"],
                "approval": ["approve", "reject"],
            },
            "server": "aiplat-stdio-kernel",
        }

    async def shutdown(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        self._shutdown = True
        return {"status": "ok"}

    # ── Thread 原语 ───────────────────────────────────────────

    async def thread_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(params.get("project_id") or "")
        requirement = str(params.get("requirement") or "")
        if not project_id or not requirement:
            raise ValueError("project_id and requirement are required")
        thread_id = f"th_{uuid.uuid4().hex[:12]}"
        session = self._create_session(thread_id)
        state = await session.start(project_id, requirement, prd_data=params.get("prd_data"))
        self._sessions[thread_id] = session
        self._states[thread_id] = state
        run_id = self._run_id_from_state(state)
        self._after_seq[thread_id] = 0
        await self._emit_events(thread_id, run_id, reset=True)
        return {"thread_id": thread_id, "state": state, "run_id": run_id}

    async def thread_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = self._require_thread(params)
        state = self._states.get(thread_id, {})
        return {"thread_id": thread_id, "state": state,
                "phase": state.get("phase") if isinstance(state, dict) else None}

    async def thread_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = self._require_thread(params)
        run_id = self._run_id_from_state(self._states.get(thread_id, {}))
        events = self._fetch_events(run_id, after_seq=int(params.get("after_seq", 0)))
        return {"thread_id": thread_id, "events": events}

    async def thread_resume(self, params: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = self._require_thread(params)
        session = self._sessions.get(thread_id)
        if session is None:
            raise ValueError(f"no session for thread {thread_id}")
        state = self._states.get(thread_id, {})
        # 从 HITL 暂停点恢复（无暂停则空操作返回当前状态）
        if state and state.get("phase") in ("awaiting_hitl", "awaiting_approval"):
            state = await session.approve(dict(state), feedback=params.get("feedback", "resume"))
            self._states[thread_id] = state
        run_id = self._run_id_from_state(state)
        await self._emit_events(thread_id, run_id)
        return {"thread_id": thread_id, "state": state, "run_id": run_id}

    async def thread_approve(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """HITL allow：批准当前审批请求并继续执行。"""
        thread_id = self._require_thread(params)
        session = self._sessions.get(thread_id)
        if session is None:
            raise ValueError(f"no session for thread {thread_id}")
        state = self._states.get(thread_id, {})
        state = await session.approve(dict(state), feedback=params.get("feedback", ""))
        self._states[thread_id] = state
        run_id = self._run_id_from_state(state)
        await self._emit_events(thread_id, run_id)
        return {"thread_id": thread_id, "state": state, "run_id": run_id}

    async def thread_reject(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """HITL deny：拒绝并带反馈继续（引擎按 reject 语义处理）。"""
        thread_id = self._require_thread(params)
        session = self._sessions.get(thread_id)
        if session is None:
            raise ValueError(f"no session for thread {thread_id}")
        state = self._states.get(thread_id, {})
        feedback = params.get("feedback", "")
        state = await session.reject(dict(state), feedback)
        self._states[thread_id] = state
        run_id = self._run_id_from_state(state)
        await self._emit_events(thread_id, run_id)
        return {"thread_id": thread_id, "state": state, "run_id": run_id}

    async def thread_rollback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = self._require_thread(params)
        session = self._sessions.get(thread_id)
        if session is None:
            raise ValueError(f"no session for thread {thread_id}")
        state = self._states.get(thread_id, {})
        stage_id = str(params.get("stage_id") or "")
        state = await session.rollback(dict(state), stage_id)
        self._states[thread_id] = state
        return {"thread_id": thread_id, "state": state}

    async def thread_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = self._require_thread(params)
        try:
            from core.api.core_facade import cancel_pipeline
            run_id = self._run_id_from_state(self._states.get(thread_id, {}))
            if run_id:
                cancel_pipeline(run_id)
        except Exception:  # noqa: BLE001 — best-effort 取消
            logger.debug("cancel failed for %s", thread_id, exc_info=True)
        return {"thread_id": thread_id, "status": "cancel_requested"}

    # ── 内部 ──────────────────────────────────────────────────

    def _require_thread(self, params: Dict[str, Any]) -> str:
        thread_id = str(params.get("thread_id") or "")
        if not thread_id:
            raise ValueError("thread_id is required")
        if thread_id not in self._sessions:
            raise ValueError(f"unknown thread {thread_id}")
        return thread_id

    def _create_session(self, thread_id: str) -> Any:
        from core.api.core_facade import create_pipeline_session
        from core.schemas_builder import PipelineConfig

        config = PipelineConfig()
        return create_pipeline_session(config)

    @staticmethod
    def _run_id_from_state(state: Any) -> str:
        if isinstance(state, dict):
            return str(state.get("run_id") or state.get("_run_id") or "")
        return ""

    def _fetch_events(self, run_id: str, after_seq: int = 0) -> list:
        if not run_id:
            return []
        try:
            from core.api.core_facade import get_pipeline_run_store
            store = get_pipeline_run_store()
            if store is None:
                return []
            events = store.list_run_events(run_id, limit=5000)
            return [e for e in events if int(e.get("seq", 0)) > after_seq]
        except Exception:  # noqa: BLE001 — 事件获取 best-effort
            logger.debug("fetch events failed", exc_info=True)
            return []

    async def _emit_events(self, thread_id: str, run_id: str, reset: bool = False) -> None:
        """拉取 run_events 并推送到 stdout（item.event 流式）。"""
        after = 0 if reset else self._after_seq.get(thread_id, 0)
        events = self._fetch_events(run_id, after_seq=after)
        for ev in events:
            self._write_line({
                "jsonrpc": JSONRPC_VERSION,
                "method": "item.event",
                "params": {"thread_id": thread_id, "event": ev},
            })
            self._after_seq[thread_id] = int(ev.get("seq", 0))

    @staticmethod
    def _write_line(obj: Dict[str, Any]) -> None:
        try:
            sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001 — 管道断开则静默
            logger.debug("stdout write failed", exc_info=True)


_METHODS = {
    "initialize": "initialize",
    "shutdown": "shutdown",
    "thread/start": "thread_start",
    "thread/status": "thread_status",
    "thread/events": "thread_events",
    "thread/resume": "thread_resume",
    "thread/approve": "thread_approve",
    "thread/reject": "thread_reject",
    "thread/rollback": "thread_rollback",
    "thread/cancel": "thread_cancel",
}


async def handle_request(kernel: StdioKernel, request: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-RPC 2.0 请求分发。"""
    req_id = request.get("id")
    method = str(request.get("method") or "")
    params = request.get("params") or {}
    if isinstance(params, list):
        params = params[0] if params else {}

    handler_name = _METHODS.get(method)
    if handler_name is None:
        return _error(req_id, -32601, f"Method not found: {method}")
    try:
        handler = getattr(kernel, handler_name)
        result = await handler(params)
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}
    except ValueError as e:
        return _error(req_id, -32602, str(e))
    except Exception as e:  # noqa: BLE001 — JSON-RPC 错误信封
        logger.warning("method %s failed: %s", method, e)
        return _error(req_id, -32603, f"Internal error: {str(e)[:300]}")


def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id,
            "error": {"code": code, "message": message}}


async def _event_loop(kernel: StdioKernel) -> None:
    """主循环：逐行读 stdin → 分发 → 写 stdout。"""
    while not kernel._shutdown:
        try:
            line = sys.stdin.readline()
        except Exception:  # noqa: BLE001, cleanup-best-effort — stdin 读取异常即结束循环
            logger.debug("stdin read failed", exc_info=True)
            break
        if not line:
            break  # EOF
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            StdioKernel._write_line(_error(None, -32700, "Parse error"))
            continue
        # 背压：并发超限返回 -32001（指数退避语义）
        async with kernel._concurrent:
            if kernel._concurrent.value > MAX_CONCURRENT:
                StdioKernel._write_line(_error(request.get("id"), ERR_SERVER_OVERLOADED,
                                               "server overloaded, retry with backoff"))
                continue
            resp = await handle_request(kernel, request)
            if resp.get("id") is not None or "error" in resp:
                StdioKernel._write_line(resp)


def main() -> None:
    """Entry: python -m core.acp.stdio_server"""
    logging.basicConfig(level=os.environ.get("AIPLAT_STDIO_LOG", "WARNING"))
    kernel = StdioKernel()
    try:
        asyncio.run(_event_loop(kernel))
    except KeyboardInterrupt:  # noqa: normal-cancellation
        pass


if __name__ == "__main__":
    main()
