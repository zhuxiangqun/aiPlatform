from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Any, List

from fastapi import APIRouter, Depends, HTTPException

from core.api.core_facade import KernelRuntime  # P0-A2: 经 CoreFacade
from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _iso(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.utcfromtimestamp(float(ts)).isoformat()
    except Exception:
        return None


async def _load_execution_record(store: Any, execution_id: str) -> Optional[Dict[str, Any]]:
    """Prefer agent_executions, then skill_executions."""
    try:
        rec = await store.get_agent_execution(execution_id)
        if rec:
            return {"kind": "agent", **rec}
    except Exception:  # noqa: cleanup-best-effort
        pass
    getter = getattr(store, "get_skill_execution", None)
    if callable(getter):
        try:
            rec = await getter(execution_id)
            if rec:
                return {"kind": "skill", **rec}
        except Exception:  # noqa: cleanup-best-effort
            pass
    return None


async def _syscall_spans(store: Any, execution_id: str, trace_id: str) -> List[Dict[str, Any]]:
    """Build span-like rows from syscall_events when traces.spans is empty."""
    lister = getattr(store, "list_syscall_events", None)
    if not callable(lister):
        return []
    try:
        items = await lister(run_id=execution_id, limit=200)
    except TypeError:
        try:
            items = await lister(execution_id, 200)
        except Exception:
            return []
    except Exception:
        return []
    if isinstance(items, dict):
        items = items.get("items") or items.get("events") or []
    spans: List[Dict[str, Any]] = []
    for ev in items or []:
        if not isinstance(ev, dict):
            continue
        kind = ev.get("kind") or ev.get("type") or "event"
        name = ev.get("name") or ev.get("skill_name") or ev.get("tool_name") or kind
        spans.append({
            "span_id": ev.get("span_id") or ev.get("id") or f"span-{len(spans)}",
            "trace_id": trace_id,
            "parent_span_id": ev.get("parent_span_id"),
            "name": f"{kind}:{name}" if kind and name and not str(name).startswith(str(kind)) else str(name),
            "kind": kind,
            "status": ev.get("status") or "unknown",
            "start_time": ev.get("start_time") or ev.get("ts") or ev.get("created_at"),
            "end_time": ev.get("end_time"),
            "duration_ms": ev.get("duration_ms"),
            "attributes": {
                "execution_id": execution_id,
                "source": "syscall_events",
            },
        })
    return spans


async def _heal_or_synthesize_trace(
    store: Any,
    execution_id: str,
    trace_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Workspace agents historically wrote agent_executions.trace_id without upsert_trace.
    Heal by upserting a traces row + attaching syscall spans so Links UI can render.
    """
    rec = await _load_execution_record(store, execution_id)
    if not rec:
        return None
    kind = rec.get("kind") or "agent"
    name_key = rec.get("agent_id") or rec.get("skill_name") or execution_id
    start = rec.get("start_time") or rec.get("created_at")
    end = rec.get("end_time")
    status = rec.get("status") or "unknown"
    duration_ms = rec.get("duration_ms")
    try:
        await store.upsert_trace({
            "trace_id": trace_id,
            "name": f"{kind}:{name_key}",
            "status": "completed" if status == "completed" else status,
            "start_time": float(start) if start is not None else None,
            "end_time": float(end) if end is not None else None,
            "duration_ms": duration_ms,
            "attributes": {
                "execution_id": execution_id,
                "agent_id": rec.get("agent_id"),
                "skill_name": rec.get("skill_name"),
                "source": "synthesized_from_execution",
            },
        })
    except Exception:  # noqa: cleanup-best-effort
        pass
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        trace = {
            "trace_id": trace_id,
            "name": f"{kind}:{name_key}",
            "status": status,
            "start_time": start,
            "end_time": end,
            "duration_ms": duration_ms,
            "attributes": {"execution_id": execution_id, "source": "synthesized_from_execution"},
            "spans": [],
        }
    spans = trace.get("spans") or []
    if not spans:
        spans = await _syscall_spans(store, execution_id, trace_id)
        trace["spans"] = spans
    return trace


@router.get("/executions/{execution_id}/trace", response_model=Dict[str, Any])
async def get_trace_by_execution(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get trace (with spans) by execution_id (agent/skill)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace_id = await store.get_trace_id_by_execution_id(execution_id)
    if not trace_id:
        # Last resort: invent stable id from execution so heal path can still run
        rec = await _load_execution_record(store, execution_id)
        if not rec:
            raise HTTPException(status_code=404, detail=f"Trace not found for execution {execution_id}")
        trace_id = rec.get("trace_id") or f"trace-synth-{execution_id}"
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        trace = await _heal_or_synthesize_trace(store, execution_id, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    # Prefer syscall spans when persisted spans empty (common for workspace agents)
    if not (trace.get("spans") or []):
        synth = await _syscall_spans(store, execution_id, trace_id)
        if synth:
            trace["spans"] = synth
    trace["start_time"] = _iso(trace.get("start_time"))
    trace["end_time"] = _iso(trace.get("end_time"))
    return trace


@router.get("/executions/{execution_id}/status", response_model=Dict[str, Any])
async def get_execution_status(execution_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get agent/skill/run_graph execution status (for frontend polling).

    Lookup order: agent_executions → skill_executions → run_graph_meta → run_events.
    Missing records return 200 + ``not_found`` (not 404) so live pollers do not spam
    console errors for short-lived or graph-only runs.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    eid = str(execution_id or "").strip()
    record = await store.get_agent_execution(eid) if eid else None
    kind = "agent"
    if not record:
        try:
            record = await store.get_skill_execution(eid)
            kind = "skill"
        except Exception:
            record = None
    if record:
        return {
            "execution_id": eid,
            "kind": kind,
            "status": record.get("status", "unknown"),
            "end_time": record.get("end_time"),
            "duration_ms": record.get("duration_ms"),
            "output": record.get("output"),
            "error": record.get("error"),
            "not_found": False,
        }

    # Authoritative RunGraph projection (Skill/Agent may finish graph before row upsert races)
    try:
        rg_status = await store.get_run_graph_status(eid) if eid and hasattr(store, "get_run_graph_status") else None
    except Exception:
        rg_status = None
    if rg_status:
        st = str(rg_status).lower()
        if st in ("completed", "ok", "success", "done"):
            mapped = "completed"
        elif st in ("failed", "error", "timeout"):
            mapped = "failed" if st != "timeout" else "timeout"
        else:
            mapped = st or "running"
        return {
            "execution_id": eid,
            "kind": "run_graph",
            "status": mapped,
            "end_time": None,
            "duration_ms": None,
            "output": None,
            "error": None,
            "not_found": False,
        }

    try:
        if eid and hasattr(store, "has_run_end") and await store.has_run_end(run_id=eid):
            return {
                "execution_id": eid,
                "kind": "run_events",
                "status": "completed",
                "end_time": None,
                "duration_ms": None,
                "output": None,
                "error": None,
                "not_found": False,
            }
    except Exception:
        logging.debug("has_run_end check failed for %s", eid, exc_info=True)

    return {
        "execution_id": eid,
        "kind": None,
        "status": "unknown",
        "end_time": None,
        "duration_ms": None,
        "output": None,
        "error": None,
        "not_found": True,
    }
