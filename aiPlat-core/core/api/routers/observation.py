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


@router.get("/runs/{run_id}/graph", response_model=Dict[str, Any])
async def get_run_graph(run_id: str):
    """Authoritative RunGraph projection for ExecutionViewer."""
    from core.harness.observation.run_graph import get_graph
    return await get_graph(run_id)


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

        # Phase 0.5: replay authoritative RunGraph (preferred by ExecutionViewer)
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        seen_ids: set = set()
        seen_graph_nodes: set = set()
        has_graph = False
        try:
            from core.harness.observation.run_graph import get_graph as _get_rg
            g = await _get_rg(run_id)
            has_graph = bool(g.get("has_graph"))
            if has_graph:
                nodes = g.get("nodes") or []
                yield f"data: {_json.dumps({'type': 'replay_start', 'source': 'run_graph', 'count': len(nodes)})}\n\n"
                for node in nodes:
                    nid = str((node or {}).get("node_id") or "")
                    if nid:
                        seen_graph_nodes.add(nid)
                    yield f"data: {_json.dumps({'type': 'graph_upsert', 'run_id': run_id, 'node': node}, default=str)}\n\n"
                st = g.get("status")
                if st and st not in ("running", None, ""):
                    yield f"data: {_json.dumps({'type': 'graph_done', 'run_id': run_id, 'status': st})}\n\n"
                    yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                    return
                yield f"data: {_json.dumps({'type': 'replay_done', 'source': 'run_graph'})}\n\n"
        except Exception as e:
            logging.debug("run_graph replay failed: %s", e, exc_info=True)

        # Phase 1: replay historical syscall events from SQLite (legacy / audit trail)
        if store:
            try:
                existing = await store.list_syscall_events(run_id=run_id, limit=200)
                items = existing.get("items") or existing.get("events") or []
                yield f"data: {_json.dumps({'type': 'replay_start', 'count': len(items)})}\n\n"
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
                # Already finished before SSE connected → close immediately
                # (avoid 2s heartbeat wait that leaves FE badge stuck on "running")
                if hasattr(store, "has_run_end") and await store.has_run_end(run_id=run_id):
                    yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                    return
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        # Phase 2: live streaming from EventBus (if active), else signal done
        q = EventBus.subscribe(run_id)
        try:
            yield f"data: {_json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=2)
                    if isinstance(event, dict) and event.get("type") in ("graph_upsert", "graph_done"):
                        if event.get("type") == "graph_upsert":
                            nid = str(((event.get("node") or {}) if isinstance(event.get("node"), dict) else {}).get("node_id") or "")
                            if nid:
                                seen_graph_nodes.add(nid)
                        yield f"data: {_json.dumps(event, default=str)}\n\n"
                        if event.get("type") == "graph_done":
                            yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                            return
                        continue
                    eid = event.get("id") if isinstance(event, dict) else None
                    if eid and eid in seen_ids:
                        continue  # skip duplicate from EventBus
                    if eid:
                        seen_ids.add(eid)
                    yield f"data: {_json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Poll RunGraph for missed upserts (thread-isolated agent runs)
                    if store and hasattr(store, "list_run_graph_nodes"):
                        try:
                            nodes = await store.list_run_graph_nodes(run_id)
                            for node in nodes or []:
                                nid = str((node or {}).get("node_id") or "")
                                key = f"{nid}:{(node or {}).get('status')}:{(node or {}).get('updated_at')}"
                                if key in seen_graph_nodes:
                                    continue
                                if nid:
                                    seen_graph_nodes.add(key)
                                yield f"data: {_json.dumps({'type': 'graph_upsert', 'run_id': run_id, 'node': node}, default=str)}\n\n"
                            gst = await store.get_run_graph_status(run_id) if hasattr(store, "get_run_graph_status") else None
                            if gst and gst not in ("running", None, ""):
                                yield f"data: {_json.dumps({'type': 'graph_done', 'run_id': run_id, 'status': gst})}\n\n"
                                yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                                return
                        except Exception as e:
                            logging.debug("observation graph poll failed: %s", e, exc_info=True)
                    # Pull newly persisted syscall events (covers thread-isolated agent runs
                    # where EventBus may miss, and keeps UI live during long LLM calls).
                    if store:
                        try:
                            snap = await store.list_syscall_events(run_id=run_id, limit=200)
                            for ev in (snap.get("items") or snap.get("events") or []):
                                if not isinstance(ev, dict):
                                    continue
                                eid = ev.get("id")
                                if eid and eid in seen_ids:
                                    continue
                                if eid:
                                    seen_ids.add(eid)
                                yield f"data: {_json.dumps(ev, default=str)}\n\n"
                        except Exception as e:
                            logging.debug("observation sqlite poll failed: %s", e, exc_info=True)
                    # Only send done if queue is empty AND run has finished
                    if q.empty() and store:
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
                            # Empty syscall_events alone is NOT done — stream clients often
                            # connect before the background thread writes the first event.
                            # Termination is signaled only by run_end / graph_done / finish above.
                            pass
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

