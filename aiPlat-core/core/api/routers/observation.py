"""
Observation Router — 实时事件流 SSE 端点
为 ExecutionViewer 前端组件提供实时执行可视化数据。

流程：
  1. 前端连接 SSE → 先回放 SQLite 中已有的事件
  2. 回放完毕 → 切换到 EventBus 实时推送
  3. 对于诊断事件：从 diag_buffers 回放
"""
from __future__ import annotations
import logging

import asyncio
import json as _json
import time as _time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade
from core.harness.observation.event_bus import EventBus  # noqa: facade-miss — CoreFacade 未模块级 re-export

router = APIRouter(prefix="/observation", tags=["observation"])

# Per-run_id event buffer for diagnostics events (keeps events for 60s after completion).
# Bounded by _DIAG_TTL + _MAX_DIAG_RUNS: stale entries are swept on every store.
_DIAG_TTL = 60.0
_MAX_DIAG_RUNS = 256
_diag_buffers: Dict[str, List[Dict[str, Any]]] = {}
_diag_buffer_ts: Dict[str, float] = {}


def _sweep_stale_diag_buffers() -> None:
    """Drop expired buffers (TTL) and evict oldest when over _MAX_DIAG_RUNS.

    Runs on every store_diag_event so the registry stays bounded even when a
    run never receives an explicit cleanup event.
    """
    now = _time.time()
    stale = [rid for rid, ts in _diag_buffer_ts.items() if now - ts > _DIAG_TTL]
    for rid in stale:
        _diag_buffers.pop(rid, None)
        _diag_buffer_ts.pop(rid, None)
    if len(_diag_buffers) > _MAX_DIAG_RUNS:
        ordered = sorted(_diag_buffer_ts.items(), key=lambda kv: kv[1])
        excess = len(_diag_buffers) - _MAX_DIAG_RUNS
        for rid, _ in ordered[:excess]:
            _diag_buffers.pop(rid, None)
            _diag_buffer_ts.pop(rid, None)


def store_diag_event(run_id: str, event: Dict[str, Any]) -> None:
    """Store a diagnostics event in the buffer."""
    _sweep_stale_diag_buffers()
    if run_id not in _diag_buffers:
        _diag_buffers[run_id] = []
    _diag_buffers[run_id].append(event)
    _diag_buffer_ts[run_id] = _time.time()


def get_diag_events(run_id: str) -> List[Dict[str, Any]]:
    """Get buffered diagnostics events for a run_id."""
    return _diag_buffers.get(run_id, [])


@router.get("/runs/{run_id}/stream", response_model=Dict[str, Any])
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
                seen_ids: set = set()
                for ev in items:
                    if isinstance(ev, dict):
                        eid = ev.get("id")
                        if eid and eid in seen_ids:
                            continue  # skip duplicate (DLQ double-write)
                        if eid:
                            seen_ids.add(eid)
                        yield f"data: {_json.dumps(ev, default=str)}\n\n"
                    else:
                        yield f"data: {_json.dumps(dict(ev), default=str)}\n\n"
                yield f"data: {_json.dumps({'type': 'replay_done'})}\n\n"
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        # Phase 2: live streaming from EventBus (if active), else signal done
        q = EventBus.subscribe(run_id)
        try:
            yield f"data: {_json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=2)
                    eid = event.get("id") if isinstance(event, dict) else None
                    if eid and eid in seen_ids:
                        continue  # skip duplicate from EventBus
                    if eid:
                        seen_ids.add(eid)
                    yield f"data: {_json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Only send done if queue is empty AND run has finished
                    if q.empty():
                        try:
                            # Check for finish events (MCP, diagnostics)
                            finish_events = await store.list_syscall_events(
                                run_id=run_id, name="finish", limit=1
                            )
                            items = (finish_events.get("items") or [])
                            if items and items[0].get("status") in ("ok", "error"):
                                yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                                return
                            # Check for run_end events (agent/skill/tool executions)
                            if hasattr(store, "has_run_end"):
                                if await store.has_run_end(run_id=run_id):
                                    yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                                    return
                            # If no events at all, also done (stale run_id)
                            any_events = await store.list_syscall_events(run_id=run_id, limit=1)
                            if not (any_events.get("items") or []):
                                yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                                return
                        except Exception as e:
                            logging.warning(str(e), exc_info=True)
                    yield f"data: {_json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass  # noqa: normal-cancellation
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

