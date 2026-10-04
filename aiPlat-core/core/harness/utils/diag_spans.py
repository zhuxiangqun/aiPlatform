"""Synthesize Links/Trace spans from syscall_events + run_graph_nodes.

Workspace agents rarely write TraceService span rows; diagnostics heal by projecting
observation stores into span-shaped dicts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


async def syscall_spans(store: Any, execution_id: str, trace_id: str) -> List[Dict[str, Any]]:
    """Build span-like rows from syscall_events."""
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
        kind = str(ev.get("kind") or ev.get("type") or "").strip()
        name = str(ev.get("name") or ev.get("skill_name") or ev.get("tool_name") or "").strip()
        # Drop EventBus DLQ ghosts: empty kind/name SSE envelopes persisted as
        # syscall_events (UI showed event/unknown after agent_end).
        if not kind and not name:
            continue
        kind = kind or "event"
        name = name or kind
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


async def run_graph_spans(store: Any, execution_id: str, trace_id: str) -> List[Dict[str, Any]]:
    """Project run_graph_nodes into span-like rows."""
    lister = getattr(store, "list_run_graph_nodes", None)
    if not callable(lister):
        return []
    try:
        nodes = await lister(execution_id)
    except TypeError:
        try:
            nodes = await lister(run_id=execution_id)
        except Exception:
            return []
    except Exception:
        return []
    if isinstance(nodes, dict):
        nodes = nodes.get("nodes") or nodes.get("items") or []
    spans: List[Dict[str, Any]] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        node_id = str(n.get("node_id") or n.get("id") or f"rg-{len(spans)}")
        kind = str(n.get("kind") or "run_graph")
        name = str(n.get("name") or n.get("label") or kind)
        spans.append({
            "span_id": f"rg:{node_id}",
            "trace_id": trace_id,
            "parent_span_id": (f"rg:{n['parent_id']}" if n.get("parent_id") else None),
            "name": f"{kind}:{name}" if name and not name.startswith(kind) else name,
            "kind": kind,
            "status": n.get("status") or "unknown",
            "start_time": n.get("start_time") or n.get("opened_at"),
            "end_time": n.get("end_time") or n.get("closed_at"),
            "duration_ms": n.get("duration_ms"),
            "attributes": {
                "execution_id": execution_id,
                "source": "run_graph_nodes",
                "node_id": node_id,
                "role": n.get("role"),
            },
        })
    return spans


async def merged_diag_spans(
    store: Any,
    execution_id: str,
    trace_id: str,
    *,
    existing: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Union existing + syscall + run_graph spans for Links Trace."""
    by_key: Dict[str, Dict[str, Any]] = {}
    for s in existing or []:
        if isinstance(s, dict):
            key = str(s.get("span_id") or s.get("name") or id(s))
            by_key[key] = s
    for s in await syscall_spans(store, execution_id, trace_id):
        key = str(s.get("span_id") or s.get("name") or id(s))
        by_key.setdefault(key, s)
    for s in await run_graph_spans(store, execution_id, trace_id):
        key = str(s.get("span_id") or s.get("name") or id(s))
        by_key[key] = s
    out = list(by_key.values())

    def _sort_key(row: Dict[str, Any]) -> float:
        try:
            return float(row.get("start_time") or 0.0)
        except Exception:
            return 0.0

    out.sort(key=_sort_key)
    return out
