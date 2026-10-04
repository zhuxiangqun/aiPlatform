"""
RunGraph — authoritative execution-tree projection for ExecutionViewer.

Write path (emitters):
  open_node / close_node / upsert_node / mark_run_done

Read path (UI):
  get_graph(run_id) → { status, nodes, roots }

Audit path:
  still appends syscall_events (best-effort) for diagnostics / OTel.
  EventBus publishes graph_upsert / graph_done for SSE.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.run_graph")

_TERMINAL = frozenset({"ok", "success", "completed", "done", "error", "failed", "timeout", "cancelled", "canceled"})


def _store():
    try:
        from core.services.execution_store import get_execution_store
        return get_execution_store()
    except Exception:
        _log.debug("get_execution_store failed", exc_info=True)
        return None


def _normalize_status(status: str, *, opening: bool = False) -> str:
    s = (status or "").strip().lower()
    if opening:
        return "running"
    if s in ("ok", "success", "completed", "done", "finished", "observing", "eval", "decision", "selected"):
        return "ok"
    if s in ("error", "failed", "timeout", "cancelled", "canceled", "policy_denied", "blocked"):
        return "error"
    if s in ("warning", "approval_required"):
        return "warning"
    if s in ("running", "pending", "accepted", "thinking", "acting"):
        return "running"
    return s or "running"


def _publish(run_id: str, event: Dict[str, Any]) -> None:
    try:
        from core.harness.observation.event_bus import EventBus
        EventBus.publish(str(run_id), event)
    except Exception:
        _log.debug("EventBus publish failed", exc_info=True)


async def _audit_syscall(node: Dict[str, Any], *, event_status: Optional[str] = None) -> None:
    """Best-effort append to syscall_events for audit compatibility."""
    store = _store()
    if store is None or not hasattr(store, "add_syscall_event"):
        return
    try:
        st = event_status or node.get("status") or "running"
        await store.add_syscall_event(
            {
                "id": f"rg:{node.get('run_id')}:{node.get('node_id')}:{st}:{int(time.time() * 1000)}",
                "run_id": node.get("run_id"),
                "span_id": node.get("node_id"),
                "parent_span_id": node.get("parent_id"),
                "kind": node.get("kind") or "default",
                "name": node.get("name") or "",
                "status": st,
                "start_time": node.get("start_time"),
                "end_time": node.get("end_time"),
                "duration_ms": node.get("duration_ms"),
                "args": node.get("args") or {},
                "result": node.get("result") or {},
                "error": node.get("error"),
                "target_type": node.get("kind"),
                "target_id": node.get("name"),
                "input_tokens": node.get("input_tokens") or 0,
                "output_tokens": node.get("output_tokens") or 0,
                "cost": node.get("cost") or 0,
            }
        )
    except Exception:
        _log.debug("run_graph audit syscall failed", exc_info=True)


def _to_sse_payload(node: Dict[str, Any], *, event_type: str = "graph_upsert") -> Dict[str, Any]:
    return {
        "type": event_type,
        "run_id": node.get("run_id"),
        "node": dict(node),
    }


async def open_node(
    run_id: str,
    node_id: str,
    *,
    kind: str,
    name: str,
    parent_id: Optional[str] = None,
    label: Optional[str] = None,
    role: str = "work",
    args: Optional[Dict[str, Any]] = None,
    sort_key: Optional[float] = None,
    audit: bool = True,
) -> Dict[str, Any]:
    """Create or reset a node to running."""
    store = _store()
    if store is None:
        return {}
    now = time.time()
    payload = {
        "run_id": str(run_id),
        "node_id": str(node_id),
        "parent_id": parent_id,
        "kind": kind,
        "name": name,
        "label": label or name,
        "role": role if role in ("container", "work") else "work",
        "status": "running",
        "start_time": now,
        "end_time": None,
        "duration_ms": 0,
        "args": args or {},
        "result": {},
        "error": None,
        "sort_key": sort_key if sort_key is not None else now,
        "updated_at": now,
    }
    try:
        stored = await store.upsert_run_graph_node(payload)
    except Exception:
        _log.debug("open_node upsert failed", exc_info=True)
        return {}
    _publish(str(run_id), _to_sse_payload(stored or payload))
    if audit:
        await _audit_syscall(stored or payload, event_status="running")
    return stored or payload


async def close_node(
    run_id: str,
    node_id: str,
    *,
    status: str = "ok",
    result: Any = None,
    error: Optional[str] = None,
    duration_ms: Optional[float] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
    audit: bool = True,
) -> Dict[str, Any]:
    """UPDATE node to a terminal status (ok/error/warning)."""
    store = _store()
    if store is None:
        return {}
    now = time.time()
    st = _normalize_status(status)
    if st == "running":
        st = "ok"
    existing = None
    try:
        existing = await store.get_run_graph_node(str(run_id), str(node_id))
    except Exception:
        _log.debug("close_node get failed", exc_info=True)
    start = (existing or {}).get("start_time")
    dur = duration_ms
    if dur is None and start is not None:
        try:
            dur = (now - float(start)) * 1000.0
        except Exception:
            dur = None
    payload = {
        "run_id": str(run_id),
        "node_id": str(node_id),
        "parent_id": (existing or {}).get("parent_id"),
        "kind": (existing or {}).get("kind") or "default",
        "name": (existing or {}).get("name") or node_id,
        "label": (existing or {}).get("label"),
        "role": (existing or {}).get("role") or "work",
        "status": st,
        "start_time": start,
        "end_time": now,
        "duration_ms": dur,
        "args": (existing or {}).get("args") or {},
        "result": result if result is not None else ((existing or {}).get("result") or {}),
        "error": error,
        "sort_key": (existing or {}).get("sort_key"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
        "updated_at": now,
    }
    try:
        stored = await store.upsert_run_graph_node(payload)
    except Exception:
        _log.debug("close_node upsert failed", exc_info=True)
        return {}
    _publish(str(run_id), _to_sse_payload(stored or payload))
    if audit:
        await _audit_syscall(stored or payload, event_status=st)
    return stored or payload


async def upsert_node(
    run_id: str,
    node_id: str,
    *,
    kind: Optional[str] = None,
    name: Optional[str] = None,
    parent_id: Optional[str] = None,
    label: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    error: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost: Optional[float] = None,
    audit: bool = False,
) -> Dict[str, Any]:
    """Partial update without forcing open/close semantics."""
    store = _store()
    if store is None:
        return {}
    existing = {}
    try:
        existing = await store.get_run_graph_node(str(run_id), str(node_id)) or {}
    except Exception:
        existing = {}
    if not existing and not (kind and name):
        return {}
    now = time.time()
    payload = {
        "run_id": str(run_id),
        "node_id": str(node_id),
        "parent_id": parent_id if parent_id is not None else existing.get("parent_id"),
        "kind": kind or existing.get("kind") or "default",
        "name": name or existing.get("name") or node_id,
        "label": label if label is not None else existing.get("label"),
        "role": role or existing.get("role") or "work",
        "status": _normalize_status(status) if status else (existing.get("status") or "running"),
        "start_time": existing.get("start_time") or now,
        "end_time": existing.get("end_time"),
        "duration_ms": existing.get("duration_ms"),
        "args": args if args is not None else (existing.get("args") or {}),
        "result": result if result is not None else (existing.get("result") or {}),
        "error": error if error is not None else existing.get("error"),
        "sort_key": existing.get("sort_key") or now,
        "input_tokens": int(input_tokens if input_tokens is not None else (existing.get("input_tokens") or 0)),
        "output_tokens": int(output_tokens if output_tokens is not None else (existing.get("output_tokens") or 0)),
        "cost": float(cost if cost is not None else (existing.get("cost") or 0)),
        "updated_at": now,
    }
    try:
        stored = await store.upsert_run_graph_node(payload)
    except Exception:
        _log.debug("upsert_node failed", exc_info=True)
        return {}
    _publish(str(run_id), _to_sse_payload(stored or payload))
    if audit:
        await _audit_syscall(stored or payload)
    return stored or payload


async def mark_run_done(run_id: str, status: str = "completed") -> Dict[str, Any]:
    """Mark run finished and force-close any still-running nodes."""
    store = _store()
    if store is None:
        return {"run_id": run_id, "status": status, "closed": []}
    st = "completed" if status in ("ok", "success", "completed", "done") else (
        "failed" if status in ("error", "failed", "timeout") else str(status or "completed")
    )
    node_status = "ok" if st == "completed" else "error"
    closed: List[str] = []
    try:
        closed = await store.close_running_run_graph_nodes(str(run_id), status=node_status)
    except Exception:
        _log.debug("mark_run_done close running failed", exc_info=True)
    try:
        await store.set_run_graph_status(str(run_id), st)
    except Exception:
        _log.debug("mark_run_done set status failed", exc_info=True)

    # Re-publish closed nodes so SSE clients see final status
    for nid in closed:
        try:
            node = await store.get_run_graph_node(str(run_id), nid)
            if node:
                _publish(str(run_id), _to_sse_payload(node))
        except Exception:
            _log.debug("mark_run_done republish failed", exc_info=True)

    done_evt = {
        "type": "graph_done",
        "run_id": str(run_id),
        "status": st,
        "closed": closed,
    }
    _publish(str(run_id), done_evt)
    return {"run_id": str(run_id), "status": st, "closed": closed}


def _repair_step_container_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Heal step:* rows overwritten by routing/work events (span_id collision)."""
    import re

    out: List[Dict[str, Any]] = []
    for n in nodes:
        item = dict(n)
        nid = str(item.get("node_id") or "")
        m = re.match(r"^step:([^:]+):(\d+)$", nid)
        if m:
            expected = f"step_{m.group(2)}"
            name = str(item.get("name") or "")
            kind = str(item.get("kind") or "")
            role = str(item.get("role") or "")
            corrupted = (
                name != expected
                or kind not in ("step", "")
                or role != "container"
                or str(item.get("parent_id") or "") == nid
            )
            if corrupted:
                agent_id = m.group(1)
                item["name"] = expected
                item["label"] = expected
                item["kind"] = "step"
                item["role"] = "container"
                if str(item.get("parent_id") or "") == nid or not item.get("parent_id"):
                    item["parent_id"] = f"agent:{agent_id}:start"
        out.append(item)
    return out


def _build_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        item = dict(n)
        item["children"] = []
        # UI-friendly fields aligned with ExecutionViewer ENode
        item["id"] = item.get("node_id")
        by_id[str(item["node_id"])] = item

    roots: List[Dict[str, Any]] = []
    for item in by_id.values():
        pid = item.get("parent_id")
        if pid and str(pid) in by_id and str(pid) != str(item.get("node_id")):
            parent = by_id[str(pid)]
            parent.setdefault("children", []).append(item)
            item["parentId"] = str(pid)
        else:
            roots.append(item)

    def _sort(lst: List[Dict[str, Any]]) -> None:
        lst.sort(
            key=lambda x: (
                float(x.get("sort_key") or x.get("start_time") or 0),
                str(x.get("name") or ""),
            )
        )
        for c in lst:
            if c.get("children"):
                _sort(c["children"])

    _sort(roots)
    return roots


async def get_graph(run_id: str) -> Dict[str, Any]:
    """Return authoritative graph projection for a run."""
    store = _store()
    if store is None:
        return {"run_id": run_id, "status": None, "nodes": [], "roots": [], "has_graph": False}
    try:
        nodes = await store.list_run_graph_nodes(str(run_id))
        status = await store.get_run_graph_status(str(run_id))
    except Exception:
        _log.debug("get_graph failed", exc_info=True)
        return {"run_id": run_id, "status": None, "nodes": [], "roots": [], "has_graph": False}
    nodes = _repair_step_container_nodes(nodes)
    roots = _build_tree(nodes)
    return {
        "run_id": str(run_id),
        "status": status,
        "nodes": nodes,
        "roots": roots,
        "has_graph": bool(nodes) or status is not None,
    }


async def mirror_syscall_to_graph(event: Dict[str, Any]) -> None:
    """Mirror a syscall_events row into run_graph when the run already has a graph.

    Skips run_graph's own audit rows (id prefix ``rg:``) to avoid loops.
    """
    if not isinstance(event, dict):
        return
    eid = str(event.get("id") or "")
    if eid.startswith("rg:"):
        return
    run_id = str(event.get("run_id") or "").strip()
    if not run_id:
        return
    store = _store()
    if store is None:
        return
    try:
        meta_status = await store.get_run_graph_status(run_id)
    except Exception:
        return
    if meta_status is None:
        return  # no graph for this run yet

    span_id = str(event.get("span_id") or eid or "").strip()
    name = str(event.get("name") or "unknown")
    if not span_id:
        span_id = f"{name}:{int(time.time() * 1000)}"
    # Container lifecycle is owned by open_node/close_node — skip duplicate names
    if name in ("agent_start", "agent_end", "skill_start", "skill_end"):
        return

    st = _normalize_status(str(event.get("status") or "running"))
    kind = str(event.get("kind") or "default")
    # Empty string parent is as bad as None — canvas parks the node in 「其它」.
    _raw_parent = event.get("parent_span_id")
    parent_id = _raw_parent if (_raw_parent is not None and str(_raw_parent).strip()) else None
    role = "work"
    if name.startswith("step_") or kind == "step":
        role = "container"
        kind = "step"

    node_id = span_id
    # Routing telemetry shares the skill TraceGate span_id. If we park skill_route
    # on that id first, status=selected→ok and later skill/running is refused by
    # "don't reopen closed nodes" — canvas keeps only「路由 · 选技能」(run-2e8529).
    if kind == "routing" and name in (
        "skill_route",
        "skill_candidates",
        "skill_candidates_snapshot",
    ):
        node_id = f"routing:{name}:{span_id}"
    # Never let work events reuse a ReAct/session container id (historical bug:
    # routing_decision/strict_eval sometimes arrive with span_id == step:* and
    # ON CONFLICT overwrites the step card → canvas shows「step_1 · 路由」).
    _CONTAINER_PREFIXES = ("step:", "agent:", "skill:")
    _is_container_id = any(str(node_id).startswith(p) for p in _CONTAINER_PREFIXES)
    if _is_container_id and not (
        name.startswith("step_")
        or kind == "step"
        or name in ("agent_start", "agent_end", "skill_start", "skill_end")
    ):
        # Force a distinct work id under the container
        node_id = f"{kind or 'work'}:{name}:{span_id}"
        if not parent_id:
            parent_id = span_id
    # Coalesce skill work into stable skill:{name} when executor (or prior open) already created it.
    # Prevents standalone skill runs from showing container + duplicate UUID work node.
    if kind == "skill" and name not in ("skill_start", "skill_end"):
        stable_id = f"skill:{name}"
        try:
            existing_stable = await store.get_run_graph_node(run_id, stable_id)
        except Exception:
            existing_stable = None
        if existing_stable:
            node_id = stable_id
            parent_id = existing_stable.get("parent_id")
            role = existing_stable.get("role") or "work"
    # Diagnostic context markers: always one node per name under the run.
    # Open/close historically used mismatched span_ids (prep:{agent} vs prep:react /
    # {run}:pre_llm_prep) → twin cards (running + completed). Fold into the earliest
    # existing same-name node when present; else stable ctx:{name}.
    if name in ("pre_llm_prep", "llm_enter", "context_snapshot") and kind in (
        "context",
        "default",
        "",
    ):
        node_id = f"ctx:{name}"
        try:
            twins = [
                n
                for n in await store.list_run_graph_nodes(run_id)
                if str(n.get("name") or "") == name
            ]
        except Exception:
            twins = []
        if twins:
            twins.sort(
                key=lambda n: float(n.get("start_time") or n.get("sort_key") or 0),
            )
            keep = twins[0]
            node_id = str(keep.get("node_id") or node_id)
            if keep.get("parent_id") and not parent_id:
                parent_id = keep.get("parent_id")
            # Close/ok: also seal any leftover twin ids so the canvas does not keep
            # a stale 「执行中」card alongside the completed one.
            if st in ("ok", "error", "warning") and len(twins) > 1:
                now_seal = time.time()
                for twin in twins[1:]:
                    tid = str(twin.get("node_id") or "")
                    if not tid or tid == node_id:
                        continue
                    try:
                        await store.upsert_run_graph_node(
                            {
                                "run_id": run_id,
                                "node_id": tid,
                                "parent_id": twin.get("parent_id"),
                                "kind": twin.get("kind") or kind,
                                "name": name,
                                "label": twin.get("label") or name,
                                "role": twin.get("role") or "work",
                                "status": st,
                                "start_time": twin.get("start_time") or now_seal,
                                "end_time": now_seal,
                                "duration_ms": twin.get("duration_ms") or 0,
                                "args": twin.get("args") or {},
                                "sort_key": twin.get("sort_key") or twin.get("start_time") or now_seal,
                                "updated_at": now_seal,
                            }
                        )
                    except Exception:
                        _log.debug("seal twin context marker failed", exc_info=True)

    try:
        existing = await store.get_run_graph_node(run_id, node_id)
        if existing and existing.get("status") in ("ok", "error", "warning") and st == "running":
            # Exception: skill work may arrive after skill_route(selected→ok) on the
            # same TraceGate span — must still open the Skill card.
            _allow_reopen = (
                kind == "skill"
                and name not in ("skill_start", "skill_end")
                and str(existing.get("kind") or "") == "routing"
            )
            if not _allow_reopen:
                return  # don't reopen closed nodes
        # Protect container rows: never overwrite step/agent name with routing/llm/etc.
        if existing and str(existing.get("role") or "") == "container":
            existing_name = str(existing.get("name") or "")
            if name and name != existing_name and not (
                name.startswith("step_") or name in ("agent_start", "agent_end", "skill_start", "skill_end")
            ):
                node_id = f"{kind or 'work'}:{name}:{existing.get('node_id')}"
                parent_id = existing.get("node_id") or parent_id
                existing = await store.get_run_graph_node(run_id, node_id) or {}
        # Protect skill work rows: skill_route/routing_* reuse the skill TraceGate
        # span_id and would overwrite「Skill · autoreview」→「路由 · 选技能」.
        if (
            existing
            and str(existing.get("kind") or "") == "skill"
            and str(existing.get("name") or "") not in ("skill_start", "skill_end")
            and kind == "routing"
        ):
            node_id = f"routing:{name}:{existing.get('node_id')}"
            parent_id = existing.get("parent_id") or parent_id or existing.get("node_id")
            existing = await store.get_run_graph_node(run_id, node_id) or {}
        # Reverse race: skill_route arrived first on the TraceGate span. Relocate
        # the routing card so skill can own the span id (Skill · autoreview).
        if (
            existing
            and kind == "skill"
            and name not in ("skill_start", "skill_end")
            and str(existing.get("kind") or "") == "routing"
        ):
            route_id = f"routing:{existing.get('name') or 'skill_route'}:{node_id}"
            try:
                await store.upsert_run_graph_node(
                    {
                        "run_id": run_id,
                        "node_id": route_id,
                        "parent_id": existing.get("parent_id") or parent_id,
                        "kind": "routing",
                        "name": existing.get("name") or "skill_route",
                        "label": existing.get("label") or existing.get("name") or "skill_route",
                        "role": "work",
                        "status": existing.get("status") or "ok",
                        "start_time": existing.get("start_time"),
                        "end_time": existing.get("end_time"),
                        "duration_ms": existing.get("duration_ms") or 0,
                        "args": existing.get("args") or {},
                        "result": existing.get("result") or {},
                        "sort_key": existing.get("sort_key") or existing.get("start_time"),
                        "updated_at": time.time(),
                    }
                )
            except Exception:
                _log.debug("relocate skill_route before skill claim failed", exc_info=True)
            # Fall through: overwrite node_id with the skill card
        # Self-parent is meaningless and breaks column layout
        if parent_id and str(parent_id) == str(node_id):
            parent_id = (existing or {}).get("parent_id")
            if parent_id and str(parent_id) == str(node_id):
                parent_id = None
        # Dangling / missing parent → remap invented `{run}:skill:NAME` to the
        # real skill node (UUID or skill:NAME), else adopt under latest step:*.
        # Historical bug: code_generation invented `{run}:skill:code_generation`
        # which is never opened → canvas parks generate as an orphan root.
        import re as _re_parent

        _need_adopt = False
        if parent_id:
            try:
                _pe = await store.get_run_graph_node(run_id, str(parent_id))
            except Exception:
                _pe = None
            if not _pe:
                m = _re_parent.match(
                    r"^(?:run[-_][^:]+:)?skill:(?P<sname>[^:]+)$",
                    str(parent_id),
                )
                if m:
                    sname = m.group("sname")
                    try:
                        cands = [
                            n
                            for n in await store.list_run_graph_nodes(run_id)
                            if str(n.get("kind") or "") == "skill"
                            and str(n.get("name") or "") == sname
                        ]
                    except Exception:
                        cands = []
                    if cands:
                        cands.sort(
                            key=lambda n: float(n.get("start_time") or n.get("sort_key") or 0),
                        )
                        parent_id = str(cands[-1].get("node_id") or "") or None
                    else:
                        # Prefer stable skill:{name} even if not yet listed
                        stable = f"skill:{sname}"
                        try:
                            _stn = await store.get_run_graph_node(run_id, stable)
                        except Exception:
                            _stn = None
                        if _stn:
                            parent_id = stable
                        else:
                            _need_adopt = True
                else:
                    _need_adopt = True
        if not parent_id:
            _need_adopt = kind in ("llm", "reason", "context") and name in (
                "generate", "LLM·generate", "pre_llm_prep", "llm_enter", "context_snapshot",
            )
        if _need_adopt:
            try:
                steps = [
                    n
                    for n in await store.list_run_graph_nodes(run_id)
                    if str(n.get("role") or "") == "container"
                    and str(n.get("kind") or "") == "step"
                    and str(n.get("node_id") or "").startswith("step:")
                ]
                if steps:
                    steps.sort(
                        key=lambda n: float(n.get("start_time") or n.get("sort_key") or 0),
                    )
                    parent_id = str(steps[-1].get("node_id") or "") or None
                elif not parent_id:
                    parent_id = None
                else:
                    # Keep dangling only if no step yet (early agent-level markers)
                    parent_id = parent_id if (
                        name == "context_snapshot" or kind == "agent"
                    ) else None
            except Exception:
                _log.debug("adopt dangling parent under step failed", exc_info=True)
        # Also skip creating a child skill event that only duplicates stable node under itself
        if (
            kind == "skill"
            and name not in ("skill_start", "skill_end")
            and parent_id
            and str(parent_id) == f"skill:{name}"
            and node_id != f"skill:{name}"
        ):
            # Prefer folding into the stable skill node
            node_id = f"skill:{name}"
            try:
                existing = await store.get_run_graph_node(run_id, node_id) or existing
            except Exception:  # noqa: cleanup-best-effort
                pass
            parent_id = (existing or {}).get("parent_id")

        now = time.time()
        start = event.get("start_time") or (existing or {}).get("start_time") or now
        end = event.get("end_time")
        dur = event.get("duration_ms")
        if st != "running":
            end = end or now
            if dur is None and start is not None:
                try:
                    dur = (float(end) - float(start)) * 1000.0
                except Exception:
                    dur = None
        payload = {
            "run_id": run_id,
            "node_id": node_id,
            "parent_id": parent_id if parent_id is not None else (existing or {}).get("parent_id"),
            "kind": kind,
            "name": name,
            "label": (existing or {}).get("label") or name,
            "role": role,
            "status": st if st != "running" else "running",
            "start_time": start,
            "end_time": end,
            "duration_ms": dur,
            "args": event.get("args") if isinstance(event.get("args"), dict) else ((existing or {}).get("args") or {}),
            "result": event.get("result") if event.get("result") is not None else ((existing or {}).get("result") or {}),
            "error": event.get("error") if isinstance(event.get("error"), str) else (existing or {}).get("error"),
            "sort_key": (existing or {}).get("sort_key") or start or now,
            "input_tokens": int(event.get("input_tokens") or 0),
            "output_tokens": int(event.get("output_tokens") or 0),
            "cost": float(event.get("cost") or 0),
            "updated_at": now,
        }
        stored = await store.upsert_run_graph_node(payload)
        _publish(run_id, _to_sse_payload(stored or payload))
    except Exception:
        _log.debug("mirror_syscall_to_graph failed", exc_info=True)


__all__ = [
    "open_node",
    "close_node",
    "upsert_node",
    "mark_run_done",
    "get_graph",
    "mirror_syscall_to_graph",
]
