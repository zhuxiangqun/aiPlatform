"""
Observation Router — 实时事件流 SSE 端点
为 ExecutionViewer 前端组件提供实时执行可视化数据。

流程：
  1. 前端连接 SSE → 先回放 SQLite 中已有的事件
  2. 回放完毕 → 切换到 EventBus 实时推送
  3. 对于诊断事件：从 diag_buffers 回放
"""
from __future__ import annotations

import asyncio
import json as _json
import time as _time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.observation.event_bus import EventBus

router = APIRouter(prefix="/api/core/observation", tags=["observation"])

# Per-run_id event buffer for diagnostics events (keeps events for 60s after completion)
_diag_buffers: Dict[str, List[Dict[str, Any]]] = {}
_diag_buffer_ts: Dict[str, float] = {}


def store_diag_event(run_id: str, event: Dict[str, Any]) -> None:
    """Store a diagnostics event in the buffer."""
    if run_id not in _diag_buffers:
        _diag_buffers[run_id] = []
    _diag_buffers[run_id].append(event)
    _diag_buffer_ts[run_id] = _time.time()


def get_diag_events(run_id: str) -> List[Dict[str, Any]]:
    """Get buffered diagnostics events for a run_id."""
    return _diag_buffers.get(run_id, [])


@router.get("/runs/{run_id}/stream")
async def stream_events(run_id: str):
    """SSE 实时事件流。先回放历史事件，再推送新事件。"""

    async def event_generator():
        # Phase 0: replay diagnostics events from buffer (if any)
        diag_events = get_diag_events(run_id)
        if diag_events:
            yield f"data: {_json.dumps({'type': 'replay_start', 'source': 'diag_buffer', 'count': len(diag_events)})}\n\n"
            for ev in diag_events:
                yield f"data: {_json.dumps(ev, default=str)}\n\n"
            yield f"data: {_json.dumps({'type': 'replay_done', 'source': 'diag_buffer'})}\n\n"

        # Phase 1: replay historical syscall events from SQLite
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store:
            try:
                existing = await store.list_syscall_events(run_id=run_id, limit=200)
                items = existing.get("items") or existing.get("events") or []
                yield f"data: {_json.dumps({'type': 'replay_start', 'count': len(items)})}\n\n"
                for ev in items:
                    if isinstance(ev, dict):
                        yield f"data: {_json.dumps(ev, default=str)}\n\n"
                    else:
                        yield f"data: {_json.dumps(dict(ev), default=str)}\n\n"
                yield f"data: {_json.dumps({'type': 'replay_done'})}\n\n"
            except Exception:
                pass

        # Phase 2: live streaming from EventBus
        q = EventBus.subscribe(run_id)
        try:
            yield f"data: {_json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {_json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {_json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            EventBus.unsubscribe(run_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
