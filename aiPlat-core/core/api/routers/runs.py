from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.run_contract import normalize_run_error, normalize_run_status_v2, wrap_execution_result_as_run_summary
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas import AutoEvalRequest, EvidenceDiffRequest, RunStatus

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "mcp_manager", None) if rt else None


def _workspace_mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_mcp_manager", None) if rt else None

def _split_checklist(text: Optional[str], *, max_items: int = 20) -> list[dict[str, Any]]:
    """
    Best-effort: turn a free-form Success Metrics section into checklist items.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = []
    for ln in lines:
        # strip bullets
        ln2 = ln.lstrip("-*•").strip()
        if not ln2:
            continue
        items.append({"text": ln2[:300], "status": "pending"})
        if len(items) >= max_items:
            break
    return items

async def _persona_checklist_from_template(*, store: Any, persona_template_id: str) -> list[dict[str, Any]]:
    try:
        tpl = await store.get_prompt_template(template_id=str(persona_template_id))
        if not isinstance(tpl, dict):
            return []
        meta_json = tpl.get("metadata_json")
        if not isinstance(meta_json, str) or not meta_json:
            return []
        import json as _json

        md = _json.loads(meta_json)
        secs = md.get("sections") if isinstance(md, dict) else None
        sm = (secs.get("success_metrics") if isinstance(secs, dict) else None) if isinstance(secs, dict) else None
        return _split_checklist(sm)
    except Exception:
        return []

def _summarize_output(output: Any, *, max_keys: int = 20) -> Dict[str, Any]:
    if output is None:
        return {}
    if isinstance(output, dict):
        keys = list(output.keys())
        return {"type": "dict", "keys": keys[:max_keys], "truncated": len(keys) > max_keys}
    if isinstance(output, list):
        return {"type": "list", "len": len(output)}
    s = str(output)
    return {"type": type(output).__name__, "preview": s[:500], "truncated": len(s) > 500}


def _summarize_syscalls(items: list, *, max_items: int = 30) -> list[dict[str, Any]]:
    out = []
    for it in (items or [])[:max_items]:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "kind": it.get("kind"),
                "name": it.get("name"),
                "status": it.get("status"),
                "duration_ms": it.get("duration_ms"),
                "error_code": it.get("error_code"),
                "target_type": it.get("target_type"),
                "target_id": it.get("target_id"),
                "created_at": it.get("created_at"),
            }
        )
    return out

def _diff_outputs(prev_out: Any, new_out: Any) -> Dict[str, Any]:
    """
    Best-effort output diff for reviewers. Keep it small and structured.
    """
    try:
        if isinstance(prev_out, dict) and isinstance(new_out, dict):
            pk = set(prev_out.keys())
            nk = set(new_out.keys())
            added = sorted(list(nk - pk))[:50]
            removed = sorted(list(pk - nk))[:50]
            common = sorted(list(pk & nk))[:50]
            changed = []
            for k in common:
                pv = prev_out.get(k)
                nv = new_out.get(k)
                # only compare simple scalars to avoid huge diffs
                if isinstance(pv, (str, int, float, bool, type(None))) and isinstance(nv, (str, int, float, bool, type(None))):
                    if pv != nv:
                        changed.append({"key": k, "prev": str(pv)[:200], "new": str(nv)[:200]})
                if len(changed) >= 20:
                    break
            return {"kind": "dict", "keys_added": added, "keys_removed": removed, "changed_scalars": changed}
        # fallback: compare previews
        ps = "" if prev_out is None else str(prev_out)
        ns = "" if new_out is None else str(new_out)
        return {
            "kind": "text",
            "prev_len": len(ps),
            "new_len": len(ns),
            "prev_preview": ps[:200],
            "new_preview": ns[:200],
        }
    except Exception:
        return {}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await store.get_run_summary(run_id=str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    # PR-03 + PR-02: return unified RunSummary v2 (but keep extra fields like target_type/target_id).
    legacy_status = run.get("status")
    err_code = run.get("error_code")
    try:
        if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
            err_code = (run.get("error") or {}).get("code")
    except Exception:
        pass
    status2 = normalize_run_status_v2(ok=str(legacy_status) == "completed", legacy_status=legacy_status, error_code=err_code)
    # ok: treat queued/accepted/running as ok (no error), but waiting_approval carries error
    ok2 = status2 not in {RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value, RunStatus.waiting_approval.value}
    err_obj = None
    if not ok2:
        err_obj = normalize_run_error(
            code=err_code or (run.get("error") or {}).get("code") if isinstance(run.get("error"), dict) else None,
            message=run.get("error_message") or (run.get("error") or {}).get("message") if isinstance(run.get("error"), dict) else None,
            detail=(run.get("error") or {}).get("detail") if isinstance(run.get("error"), dict) else None,
        )
    resp = dict(run)
    resp["ok"] = ok2
    resp["legacy_status"] = legacy_status
    resp["status"] = status2
    resp["error"] = None if ok2 else err_obj
    resp["output"] = run.get("output")
    return resp


@router.get("/runs/{run_id}/events")
async def list_run_events(run_id: str, after_seq: int = 0, limit: int = 200, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_run_events(run_id=str(run_id), after_seq=int(after_seq or 0), limit=int(limit or 200))


@router.get("/runs/{run_id}/cost")
async def get_run_cost(
    run_id: str,
    tenant_id: Optional[str] = None,
    limit_syscalls: int = 5000,
    baseline_run_id: Optional[str] = None,
    max_tokens_increase_pct: float = 0.2,
    rt: RuntimeDep = None,
):
    """
    Lightweight per-run cost summary derived from syscall_events.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    out = await store.get_run_cost_summary(run_id=str(run_id), tenant_id=tenant_id, limit_syscalls=int(limit_syscalls or 5000))
    if not out.get("ok", False):
        raise HTTPException(status_code=404, detail="run_not_found")
    if baseline_run_id:
        base = await store.get_run_cost_summary(run_id=str(baseline_run_id), tenant_id=tenant_id, limit_syscalls=int(limit_syscalls or 5000))
        if base.get("ok"):
            try:
                new_tt = float(((out.get("llm_tokens") or {}).get("total_tokens")) or 0.0)
                base_tt = float(((base.get("llm_tokens") or {}).get("total_tokens")) or 0.0)
            except Exception:
                new_tt = 0.0
                base_tt = 0.0
            allowed = base_tt * (1.0 + float(max_tokens_increase_pct or 0.0))
            passed = True
            if base_tt > 0:
                passed = new_tt <= allowed
            else:
                # if baseline is zero, treat any non-trivial new usage as regression
                passed = new_tt <= 1.0
            out["regression"] = {
                "baseline_run_id": str(baseline_run_id),
                "max_tokens_increase_pct": float(max_tokens_increase_pct or 0.0),
                "baseline_total_tokens": base_tt,
                "new_total_tokens": new_tt,
                "allowed_total_tokens": allowed,
                "delta_total_tokens": new_tt - base_tt,
                "passed": bool(passed),
            }
    return out


@router.get("/runs/{run_id}/children")
async def list_child_runs(run_id: str, rt: RuntimeDep = None):
    """
    P6-2: "SOP 节点 = 子 run" 原语：列出该 parent run 派生的子 run（从 run_events 推导）。
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    ev = await store.list_run_events(run_id=rid, after_seq=0, limit=500)
    items = ev.get("items") or []
    out = []
    for e in items:
        if e.get("type") != "child_run_spawned":
            continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if not p:
            continue
        out.append(
            {
                "node_id": p.get("node_id"),
                "child_run_id": p.get("child_run_id"),
                "kind": p.get("kind"),
                "target_id": p.get("target_id"),
                "created_at": e.get("created_at"),
            }
        )
    return {"run_id": rid, "items": out, "total": len(out)}


@router.get("/runs/{run_id}/graph")
async def get_run_graph(run_id: str, include_child_summaries: bool = True, after_seq: int = 0, rt: RuntimeDep = None):
    """
    Return a graph/DAG view derived from run_events:
    - nodes: SOP nodes with current child run + history (spawn events)
    - edges: depends_on relationships
    - joins: join barriers (defined/ready)
    - checkpoints: checkpoint lifecycle (requested/resolved/applied)
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    parent = await store.get_run_summary(run_id=rid)
    if not parent:
        raise HTTPException(status_code=404, detail="run_not_found")

    ev = await store.list_run_events(run_id=rid, after_seq=0, limit=5000)
    items = ev.get("items") or []
    last_seq = int(ev.get("last_seq") or 0) if isinstance(ev, dict) else 0

    # Delta: events after_seq for incremental UI updates (best-effort)
    delta_events = []
    try:
        ev2 = await store.list_run_events(run_id=rid, after_seq=int(after_seq or 0), limit=1000)
        delta_events = ev2.get("items") or []
    except Exception:
        delta_events = []
    changed_node_ids: set[str] = set()
    changed_join_ids: set[str] = set()
    changed_checkpoint_ids: set[str] = set()
    try:
        for e in delta_events:
            et = e.get("type")
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if et in {"child_run_spawned", "node_invalidated"}:
                nid = str(p.get("node_id") or "").strip()
                if nid:
                    changed_node_ids.add(nid)
            if et in {"join_defined", "join_ready"}:
                jid = str(p.get("join_id") or "").strip()
                if jid:
                    changed_join_ids.add(jid)
            if et in {"checkpoint_requested", "checkpoint_resolved", "checkpoint_applied"}:
                cid = str(p.get("checkpoint_id") or "").strip()
                if cid:
                    changed_checkpoint_ids.add(cid)
    except Exception:
        pass

    nodes: Dict[str, Dict[str, Any]] = {}
    invalidated_child_ids: set[str] = set()

    joins: Dict[str, Dict[str, Any]] = {}
    checkpoints: Dict[str, Dict[str, Any]] = {}

    for e in items:
        et = e.get("type")
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if et == "node_invalidated":
            cid = p.get("child_run_id")
            if isinstance(cid, str) and cid:
                invalidated_child_ids.add(cid)
        if et == "child_run_spawned":
            node_id = str(p.get("node_id") or "").strip()
            if not node_id:
                continue
            nd = nodes.setdefault(
                node_id,
                {
                    "node_id": node_id,
                    "depends_on": p.get("depends_on") if isinstance(p.get("depends_on"), list) else [],
                    "kind": p.get("kind"),
                    "target_id": p.get("target_id"),
                    "persona_template_id": p.get("persona_template_id"),
                    "risk_level": p.get("risk_level"),
                    "current_child_run_id": None,
                    "current_status": None,
                    "current_error_code": None,
                    "current_output_summary": None,
                    "history": [],
                },
            )
            # Update "current" from the latest spawn event.
            nd["depends_on"] = p.get("depends_on") if isinstance(p.get("depends_on"), list) else (nd.get("depends_on") or [])
            nd["kind"] = p.get("kind") or nd.get("kind")
            nd["target_id"] = p.get("target_id") or nd.get("target_id")
            nd["persona_template_id"] = p.get("persona_template_id") or nd.get("persona_template_id")
            nd["risk_level"] = p.get("risk_level") or nd.get("risk_level")
            nd["current_child_run_id"] = p.get("child_run_id")
            nd["history"].append(
                {
                    "seq": e.get("seq"),
                    "created_at": e.get("created_at"),
                    "child_run_id": p.get("child_run_id"),
                    "supersedes_child_run_id": p.get("supersedes_child_run_id"),
                    "persona_template_id": p.get("persona_template_id"),
                    "risk_level": p.get("risk_level"),
                    "triggered_by": p.get("triggered_by") if isinstance(p.get("triggered_by"), dict) else None,
                }
            )
        if et == "join_defined":
            jid = str(p.get("join_id") or "").strip()
            if not jid:
                continue
            joins[jid] = {
                "join_id": jid,
                "node_id": p.get("node_id"),
                "required_nodes": p.get("required_nodes") if isinstance(p.get("required_nodes"), list) else [],
                "mode": p.get("mode"),
                "blocking": p.get("blocking"),
                "checkpoint_on_ready": p.get("checkpoint_on_ready") if isinstance(p.get("checkpoint_on_ready"), dict) else None,
                "ready": False,
                "payload": None,
            }
        if et == "join_ready":
            jid = str(p.get("join_id") or "").strip()
            if not jid:
                continue
            j = joins.setdefault(jid, {"join_id": jid})
            j["ready"] = True
            j["payload"] = p
        if et == "checkpoint_requested":
            cid = str(p.get("checkpoint_id") or "").strip()
            if not cid:
                continue
            ck = checkpoints.setdefault(cid, {"checkpoint_id": cid})
            ck["requested"] = p
        if et == "checkpoint_resolved":
            cid = str(p.get("checkpoint_id") or "").strip()
            if not cid:
                continue
            ck = checkpoints.setdefault(cid, {"checkpoint_id": cid})
            ck["resolved"] = p
        if et == "checkpoint_applied":
            cid = str(p.get("checkpoint_id") or "").strip()
            if not cid:
                continue
            ck = checkpoints.setdefault(cid, {"checkpoint_id": cid})
            ck["applied"] = p

    # Resolve edges
    edges: list[dict[str, Any]] = []
    for node_id, nd in nodes.items():
        deps = nd.get("depends_on") if isinstance(nd.get("depends_on"), list) else []
        for dep in deps:
            d = str(dep).strip()
            if d:
                edges.append({"from": d, "to": node_id})

    # Pending checkpoints by node_id (best-effort)
    pending_checkpoints_by_node: Dict[str, list] = {}
    for ck in checkpoints.values():
        req0 = ck.get("requested") if isinstance(ck.get("requested"), dict) else None
        res0 = ck.get("resolved") if isinstance(ck.get("resolved"), dict) else None
        if not req0 or res0:
            continue
        nid = str(req0.get("node_id") or "").strip()
        if nid.startswith("redo:"):
            nid = nid.split("redo:", 1)[1].strip()
        if nid:
            pending_checkpoints_by_node.setdefault(nid, []).append(str(req0.get("checkpoint_id") or ""))

    # Topo sort for UI layout hints (best-effort, cycle-tolerant)
    indeg: Dict[str, int] = {nid: 0 for nid in nodes.keys()}
    adj: Dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for e in edges:
        a = str(e.get("from") or "").strip()
        b = str(e.get("to") or "").strip()
        if a and b and a in adj and b in indeg:
            adj[a].append(b)
            indeg[b] += 1
    q = [nid for nid, d in indeg.items() if d == 0]
    q.sort()
    order: list[str] = []
    while q:
        cur = q.pop(0)
        order.append(cur)
        for nxt in adj.get(cur, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
                q.sort()
    if len(order) != len(nodes):
        # cycle or missing nodes: append remaining deterministically
        rest = [nid for nid in nodes.keys() if nid not in order]
        rest.sort()
        order.extend(rest)
    level: Dict[str, int] = {}
    for nid in order:
        deps = nodes.get(nid, {}).get("depends_on") if isinstance(nodes.get(nid, {}).get("depends_on"), list) else []
        mx = 0
        for d in deps or []:
            dd = str(d).strip()
            mx = max(mx, (level.get(dd, 0) + 1) if dd else 0)
        level[nid] = mx

    # Optionally resolve current child run summaries (cap to avoid expensive fan-out)
    if include_child_summaries:
        for nd in list(nodes.values())[:120]:
            cid = nd.get("current_child_run_id")
            if not isinstance(cid, str) or not cid:
                continue
            try:
                s = await store.get_run_summary(run_id=str(cid))
            except Exception:
                s = None
            if isinstance(s, dict):
                nd["current_status"] = s.get("status")
                nd["current_error_code"] = s.get("error_code")
                nd["current_output_summary"] = _summarize_output(s.get("output"))
            nd["current_invalidated"] = str(cid) in invalidated_child_ids

    # Derive node state + layout hints
    def _state_from_status(st: Any) -> str:
        s = str(st or "").strip().lower()
        if not s:
            return "unknown"
        if s in {"completed", "success", "succeeded", "ok"}:
            return "completed"
        if "fail" in s or "error" in s or s in {"aborted", "timeout"}:
            return "failed"
        if s in {"queued", "accepted", "running", "in_progress"}:
            return "running"
        if "waiting" in s:
            return "waiting"
        return s

    for nid, nd in nodes.items():
        nd["layout"] = {"order": order.index(nid) if nid in order else 0, "level": int(level.get(nid, 0))}
        pend = pending_checkpoints_by_node.get(nid) or []
        if pend:
            nd["pending_checkpoints"] = pend
            nd["state"] = "waiting_checkpoint"
        elif nd.get("current_invalidated") is True:
            nd["state"] = "stale"
        else:
            nd["state"] = _state_from_status(nd.get("current_status"))

    # Sort nodes by layout order for UI consumption
    nodes_out = list(nodes.values())
    nodes_out.sort(key=lambda x: int((x.get("layout") or {}).get("order") or 0))

    # Join state
    joins_out = list(joins.values())
    for j in joins_out:
        if not isinstance(j, dict):
            continue
        j["state"] = "ready" if bool(j.get("ready")) else "waiting"

    # Checkpoint state
    checkpoints_out = list(checkpoints.values())
    for ck in checkpoints_out:
        if not isinstance(ck, dict):
            continue
        req0 = ck.get("requested") if isinstance(ck.get("requested"), dict) else None
        res0 = ck.get("resolved") if isinstance(ck.get("resolved"), dict) else None
        app0 = ck.get("applied") if isinstance(ck.get("applied"), dict) else None
        if app0:
            ck["state"] = "applied"
            ck["decision"] = app0.get("decision")
        elif res0:
            ck["state"] = "resolved"
            ck["decision"] = res0.get("decision")
        elif req0:
            ck["state"] = "requested"
            ck["decision"] = None
        else:
            ck["state"] = "unknown"
            ck["decision"] = None

    # Delta objects (best-effort): allow UI to update without fetching full graph again.
    def _node_delta_view(n: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(n or {})
        try:
            hist = out.get("history") if isinstance(out.get("history"), list) else []
            # Keep only last N history entries for delta
            out["history"] = hist[-20:] if isinstance(hist, list) else []
        except Exception:
            pass
        return out

    changed_nodes_updated = []
    try:
        sset = set(changed_node_ids)
        for n in nodes_out:
            if isinstance(n, dict) and str(n.get("node_id") or "") in sset:
                changed_nodes_updated.append(_node_delta_view(n))
        changed_nodes_updated = changed_nodes_updated[:100]
    except Exception:
        changed_nodes_updated = []

    changed_joins_updated = []
    try:
        sset = set(changed_join_ids)
        for j in joins_out:
            if isinstance(j, dict) and str(j.get("join_id") or "") in sset:
                changed_joins_updated.append(dict(j))
        changed_joins_updated = changed_joins_updated[:100]
    except Exception:
        changed_joins_updated = []

    changed_checkpoints_updated = []
    try:
        sset = set(changed_checkpoint_ids)
        for ck in checkpoints_out:
            if isinstance(ck, dict) and str(ck.get("checkpoint_id") or "") in sset:
                changed_checkpoints_updated.append(dict(ck))
        changed_checkpoints_updated = changed_checkpoints_updated[:200]
    except Exception:
        changed_checkpoints_updated = []


    return {
        "run_id": rid,
        "nodes": nodes_out,
        "topo_order": order,
        "edges": edges,
        "joins": joins_out,
        "checkpoints": checkpoints_out,
        "after_seq": int(after_seq or 0),
        "last_seq": int(last_seq or 0),
        "delta": {
            "changed_node_ids": sorted(list(changed_node_ids)),
            "changed_join_ids": sorted(list(changed_join_ids)),
            "changed_checkpoint_ids": sorted(list(changed_checkpoint_ids)),
            "nodes_updated": changed_nodes_updated,
            "joins_updated": changed_joins_updated,
            "checkpoints_updated": changed_checkpoints_updated,
        },
        "stats": {"nodes": len(nodes), "edges": len(edges), "joins": len(joins), "checkpoints": len(checkpoints)},
    }
@router.post("/runs/{run_id}/children/spawn")
async def spawn_child_run(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-2: "SOP 节点 = 子 run" 原语：在 parent run 下创建并执行一个 child run。

    Body:
      {
        "node_id": "step_b",
        "depends_on": ["step_a"],
        "kind": "skill|tool|agent|graph",
        "target_id": "...",
        "payload": {"input": {...}, "context": {...}},
        "options": {...}  // optional (pass-through into payload.options)
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    parent_id = str(run_id)
    parent = await store.get_run_summary(run_id=parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="update",
        resource_type="run",
        resource_id=parent_id,
        run_id=parent_id,
    )
    if deny:
        return deny

    body = dict(request or {}) if isinstance(request, dict) else {}
    node_id = str(body.get("node_id") or "").strip() or None
    depends_on = body.get("depends_on") if isinstance(body.get("depends_on"), list) else None
    depends_on = [str(x).strip() for x in (depends_on or []) if str(x).strip()] or None
    kind = str(body.get("kind") or "").strip().lower()
    target_id = str(body.get("target_id") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    persona_template_id = body.get("persona_template_id")
    if not isinstance(persona_template_id, str) or not persona_template_id.strip():
        try:
            ctxp = payload.get("context") if isinstance(payload, dict) and isinstance(payload.get("context"), dict) else {}
            persona_template_id = ctxp.get("persona_template_id")
        except Exception:
            persona_template_id = None
    persona_template_id = str(persona_template_id).strip() if isinstance(persona_template_id, str) and persona_template_id.strip() else None

    # P7: Persona routing (auto-select persona_template_id + risk_level) via tenant policy.
    routed = False
    routed_risk = None
    try:
        if not persona_template_id:
            # Determine tenant_id for policy lookup
            tenant_id0 = None
            try:
                ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                tenant_id0 = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None
            except Exception:
                tenant_id0 = None
            if not tenant_id0:
                tenant_id0 = (actor_from_http(http_request, body) or {}).get("tenant_id") or parent.get("tenant_id")
            rec = await store.get_tenant_policy(tenant_id=str(tenant_id0)) if tenant_id0 else None
            pol = rec.get("policy") if isinstance(rec, dict) and isinstance(rec.get("policy"), dict) else {}
            pr = pol.get("persona_routing") if isinstance(pol, dict) and isinstance(pol.get("persona_routing"), dict) else None
            if isinstance(pr, dict):
                import fnmatch

                op = f"{kind}:{target_id}"
                routes = pr.get("routes") if isinstance(pr.get("routes"), list) else []
                for r in routes:
                    if not isinstance(r, dict):
                        continue
                    m = str(r.get("match") or "").strip()
                    if not m:
                        continue
                    if fnmatch.fnmatch(op, m):
                        pt = r.get("persona_template_id")
                        if isinstance(pt, str) and pt.strip():
                            persona_template_id = pt.strip()
                            routed = True
                        rl = r.get("risk_level")
                        if isinstance(rl, str) and rl.strip():
                            routed_risk = rl.strip().lower()
                        break
                # defaults by kind (skill/tool/agent/graph) when no explicit route match
                if (not persona_template_id) and isinstance(pr.get("defaults_by_kind"), dict):
                    try:
                        dk = pr.get("defaults_by_kind") if isinstance(pr.get("defaults_by_kind"), dict) else {}
                        pt0 = dk.get(kind)
                        if isinstance(pt0, str) and pt0.strip():
                            persona_template_id = pt0.strip()
                            routed = True
                    except Exception:
                        pass
                if (not routed_risk) and isinstance(pr.get("default_risk_by_kind"), dict):
                    try:
                        drk = pr.get("default_risk_by_kind") if isinstance(pr.get("default_risk_by_kind"), dict) else {}
                        rl0 = drk.get(kind)
                        if isinstance(rl0, str) and rl0.strip():
                            routed_risk = rl0.strip().lower()
                    except Exception:
                        pass
                if (not persona_template_id) and isinstance(pr.get("default_persona_template_id"), str):
                    dpt = str(pr.get("default_persona_template_id") or "").strip()
                    if dpt:
                        persona_template_id = dpt
                        routed = True
                if (not routed_risk) and isinstance(pr.get("default_risk_level"), str):
                    drl = str(pr.get("default_risk_level") or "").strip().lower()
                    if drl:
                        routed_risk = drl
    except Exception:
        routed = routed

    if persona_template_id:
        payload = dict(payload or {})
        ctxp = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        payload["context"] = {**(ctxp or {}), "persona_template_id": persona_template_id}
        # propagate risk level to input params so PolicyGate can sample/force approvals
        if routed_risk:
            try:
                inp = payload.get("input") if isinstance(payload.get("input"), dict) else {}
                payload["input"] = {**(inp or {}), "_risk_level": str(routed_risk)}
                routed_risk = str(routed_risk)
            except Exception:
                pass
    opts = body.get("options") if isinstance(body.get("options"), dict) else None
    if opts and isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("options", dict(opts))
    if kind not in {"agent", "skill", "tool", "graph"}:
        raise HTTPException(status_code=400, detail="invalid_kind")
    if not target_id:
        raise HTTPException(status_code=400, detail="missing_target_id")

    actor = actor_from_http(http_request, body)

    def _redact(obj: Any, *, max_str: int = 2000, max_items: int = 60, depth: int = 0) -> Any:
        # allow moderately deep nested context (e.g., review_feedback.failed_items)
        if depth > 8:
            return "<truncated>"
        if obj is None:
            return None
        if isinstance(obj, (int, float, bool)):
            return obj
        if isinstance(obj, str):
            s = obj
            return s if len(s) <= max_str else (s[:max_str] + "…")
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for i, (k, v) in enumerate(list(obj.items())[:max_items]):
                kk = str(k)
                # avoid storing very large raw blobs
                if kk.lower() in {"raw", "content_raw", "binary", "bytes"}:
                    out[kk] = "<redacted>"
                    continue
                out[kk] = _redact(v, max_str=max_str, max_items=max_items, depth=depth + 1)
            if len(obj) > max_items:
                out["__truncated__"] = True
            return out
        if isinstance(obj, list):
            out = [_redact(x, max_str=max_str, max_items=max_items, depth=depth + 1) for x in obj[:max_items]]
            if len(obj) > max_items:
                out.append("<truncated>")
            return out
        return str(obj)

    # Execute child run
    resp = await _spawn_child_internal(
        store=store,
        parent=parent,
        parent_id=parent_id,
        actor=actor,
        node_id=node_id,
        depends_on=depends_on,
        kind=kind,
        target_id=target_id,
        payload=payload if isinstance(payload, dict) else {},
        extra_event_payload={
            # Store a redacted replay payload so node-level redo doesn't require the caller to resend.
            "request_payload": _redact(payload if isinstance(payload, dict) else {}),
            "request_payload_redacted": True,
            "persona_template_id": persona_template_id,
            "persona_routed": bool(routed),
            "risk_level": routed_risk,
        },
    )
    return resp


@router.post("/runs/{run_id}/joins/define")
async def define_join(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-4: Define a join barrier on a parent run.

    Body:
      {
        "join_id": "optional",
        "node_id": "join_step",
        "required_nodes": ["step_1", "step_2"],
        "mode": "all_success|all_done",
        "blocking": true,
        "checkpoint_on_ready": {
          "enabled": true,
          "title": "汇合复核",
          "risk_level": "medium",
          "blocking": true,
          "on_approved_spawn": {"node_id": "next_step", "kind": "skill", "target_id": "...", "payload": {...}, "depends_on": ["step_1","step_2"]},
          "on_rejected_redo_node": {"node_id": "step_1", "patch": {"input": {...}}, "reason": "fix upstream"}
        }
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    parent_id = str(run_id)
    parent = await store.get_run_summary(run_id=parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="update",
        resource_type="run",
        resource_id=parent_id,
        run_id=parent_id,
    )
    if deny:
        return deny
    body = dict(request or {}) if isinstance(request, dict) else {}
    from core.utils.ids import new_prefixed_id

    join_id = str(body.get("join_id") or new_prefixed_id("join"))
    node_id = str(body.get("node_id") or "").strip() or None
    required = body.get("required_nodes") if isinstance(body.get("required_nodes"), list) else []
    required = [str(x).strip() for x in required if str(x).strip()]
    if not required:
        raise HTTPException(status_code=400, detail="required_nodes_empty")
    mode = str(body.get("mode") or "all_success").strip().lower()
    if mode not in {"all_success", "all_done"}:
        mode = "all_success"
    blocking = bool(body.get("blocking", True))
    ck = body.get("checkpoint_on_ready") if isinstance(body.get("checkpoint_on_ready"), dict) else None
    if ck is not None:
        ck = dict(ck)
        ck.setdefault("enabled", True)
    actor = actor_from_http(http_request, body)
    await store.append_run_event(
        run_id=parent_id,
        event_type="join_defined",
        trace_id=parent.get("trace_id"),
        tenant_id=actor.get("tenant_id") or parent.get("tenant_id"),
        payload={
            "join_id": join_id,
            "node_id": node_id,
            "required_nodes": required,
            "mode": mode,
            "blocking": blocking,
            "checkpoint_on_ready": ck,
            "requested_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
        },
    )
    return {"status": "ok", "run_id": parent_id, "join_id": join_id}


@router.post("/runs/{run_id}/joins/{join_id}/wait")
async def wait_join(run_id: str, join_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-4: Long-poll until join is ready.
    It will emit join_ready once, then return.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    parent_id = str(run_id)
    parent = await store.get_run_summary(run_id=parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="update",
        resource_type="run",
        resource_id=parent_id,
        run_id=parent_id,
    )
    if deny:
        return deny
    timeout_ms = int((request or {}).get("timeout_ms") or 30000)
    after_seq = int((request or {}).get("after_seq") or 0)
    deadline = time.time() + max(1, timeout_ms) / 1000.0

    async def _find_join_def() -> Optional[Dict[str, Any]]:
        ev = await store.list_run_events(run_id=parent_id, after_seq=0, limit=2000)
        items = ev.get("items") or []
        for e in reversed(items):
            if e.get("type") != "join_defined":
                continue
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if str(p.get("join_id") or "") == str(join_id):
                return p
        return None

    jdef = await _find_join_def()
    if not jdef:
        raise HTTPException(status_code=404, detail="join_not_found")
    required = jdef.get("required_nodes") if isinstance(jdef.get("required_nodes"), list) else []
    required = [str(x).strip() for x in required if str(x).strip()]
    mode = str(jdef.get("mode") or "all_success").strip().lower()
    if mode not in {"all_success", "all_done"}:
        mode = "all_success"
    ck_def = jdef.get("checkpoint_on_ready") if isinstance(jdef.get("checkpoint_on_ready"), dict) else None
    ck_def = dict(ck_def) if isinstance(ck_def, dict) else None
    ck_enabled = bool((ck_def or {}).get("enabled", False)) if ck_def is not None else False

    # Build node->latest child mapping
    def _latest_child_by_node(items: list) -> Dict[str, str]:
        m: Dict[str, str] = {}
        for e in items:
            if e.get("type") != "child_run_spawned":
                continue
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            n = str(p.get("node_id") or "")
            cid = str(p.get("child_run_id") or "")
            if n and cid:
                m[n] = cid
        return m

    # quick path: if join_ready already exists
    ev0 = await store.list_run_events(run_id=parent_id, after_seq=0, limit=2000)
    for e in reversed(ev0.get("items") or []):
        if e.get("type") == "join_ready":
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if str(p.get("join_id") or "") == str(join_id):
                return {
                    "status": "ok",
                    "run_id": parent_id,
                    "join_id": str(join_id),
                    "ready": True,
                    "payload": p,
                    "checkpoint_id": p.get("checkpoint_id"),
                    "last_seq": ev0.get("last_seq"),
                }

    last_seq = after_seq
    actor = actor_from_http(http_request, request if isinstance(request, dict) else None)
    while time.time() < deadline:
        ev = await store.list_run_events(run_id=parent_id, after_seq=0, limit=2000)
        items = ev.get("items") or []
        last_seq = int(ev.get("last_seq") or last_seq)
        mapping = _latest_child_by_node(items)

        statuses = []
        all_done = True
        all_success = True
        missing = []
        for n in required:
            cid = mapping.get(n)
            if not cid:
                all_done = False
                all_success = False
                missing.append(n)
                continue
            rs = await store.get_run_summary(run_id=str(cid))
            st = (rs or {}).get("status") if isinstance(rs, dict) else None
            err_code = (rs or {}).get("error_code") if isinstance(rs, dict) else None
            # ExecutionStore.get_run_summary does not always include "ok"; derive best-effort.
            ok = bool(st == "completed" and not (str(err_code or "").strip()))
            statuses.append({"node_id": n, "child_run_id": cid, "status": st, "ok": ok})
            if st not in {"completed", "failed", "aborted", "timeout"}:
                all_done = False
            if st != "completed" or ok is not True:
                all_success = False

        ready = all_success if mode == "all_success" else all_done
        if ready:
            # Persona summary (best-effort): derive from parent child_run_spawned payload + prompt_templates metadata.
            personas = []
            checklist = []
            try:
                # mapping node -> latest spawn payload
                latest_payload_by_node: Dict[str, Dict[str, Any]] = {}
                for e0 in items:
                    if e0.get("type") != "child_run_spawned":
                        continue
                    p0 = e0.get("payload") if isinstance(e0.get("payload"), dict) else {}
                    nid0 = str(p0.get("node_id") or "")
                    if nid0:
                        latest_payload_by_node[nid0] = p0
                for n in required:
                    p0 = latest_payload_by_node.get(n) or {}
                    ptid = p0.get("persona_template_id")
                    ptid = str(ptid).strip() if isinstance(ptid, str) and ptid.strip() else None
                    if not ptid:
                        continue
                    tpl = await store.get_prompt_template(template_id=str(ptid))
                    md = {}
                    if isinstance(tpl, dict) and isinstance(tpl.get("metadata_json"), str) and tpl.get("metadata_json"):
                        try:
                            import json as _json

                            md = _json.loads(str(tpl.get("metadata_json") or "{}"))
                        except Exception:
                            md = {}
                    disp = (md.get("display") if isinstance(md, dict) else None) if isinstance(md, dict) else None
                    secs = (md.get("sections") if isinstance(md, dict) else None) if isinstance(md, dict) else None
                    personas.append(
                        {
                            "node_id": n,
                            "persona_template_id": ptid,
                            "name": (disp or {}).get("name") if isinstance(disp, dict) else None,
                            "vibe": (disp or {}).get("vibe") if isinstance(disp, dict) else None,
                            "success_metrics": (secs or {}).get("success_metrics") if isinstance(secs, dict) else None,
                        }
                    )
                    # checklist per persona (flatten, prefix with node_id)
                    try:
                        for it0 in _split_checklist((secs or {}).get("success_metrics") if isinstance(secs, dict) else None, max_items=10):
                            checklist.append({"text": f"[{n}] {it0.get('text')}", "status": "pending"})
                    except Exception:
                        pass
            except Exception:
                personas = []
                checklist = []

            payload = {
                "join_id": str(join_id),
                "node_id": jdef.get("node_id"),
                "mode": mode,
                "required_nodes": required,
                "statuses": statuses,
                "missing": missing,
                "personas": personas,
                "checklist": checklist[:30],
                "resolved_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
            }
            checkpoint_id = None
            # Optional: automatically request a checkpoint when join becomes ready (human-in-the-loop).
            if ck_enabled:
                try:
                    # idempotency: if checkpoint already requested for this join_id, reuse it.
                    existing = None
                    for e0 in reversed(items):
                        if e0.get("type") != "checkpoint_requested":
                            continue
                        pp = e0.get("payload") if isinstance(e0.get("payload"), dict) else {}
                        if str(pp.get("join_id") or "") == str(join_id):
                            existing = pp
                            break
                    if isinstance(existing, dict) and existing.get("checkpoint_id"):
                        checkpoint_id = existing.get("checkpoint_id")
                    else:
                        from core.utils.ids import new_prefixed_id

                        checkpoint_id = new_prefixed_id("ckpt")
                        # Best-effort: persist checklist/personas on checkpoint_requested (not only inside artifact).
                        checklist0 = None
                        personas0 = None
                        try:
                            checklist0 = payload.get("checklist") if isinstance(payload.get("checklist"), list) else None
                            personas0 = payload.get("personas") if isinstance(payload.get("personas"), list) else None
                        except Exception:
                            checklist0 = None
                            personas0 = None
                        await store.append_run_event(
                            run_id=parent_id,
                            event_type="checkpoint_requested",
                            trace_id=parent.get("trace_id"),
                            tenant_id=actor.get("tenant_id") or parent.get("tenant_id"),
                            payload={
                                "checkpoint_id": checkpoint_id,
                                "node_id": (ck_def or {}).get("node_id") or jdef.get("node_id") or "join",
                                "title": (ck_def or {}).get("title") or "汇合复核",
                                "artifact": {"type": "join_ready", "join_id": str(join_id), "payload": payload},
                                "risk_level": (ck_def or {}).get("risk_level") or "medium",
                                "blocking": bool((ck_def or {}).get("blocking", True)),
                                "join_id": str(join_id),
                                "checklist": checklist0,
                                "personas": personas0,
                                "on_approved_spawn": (ck_def or {}).get("on_approved_spawn") if isinstance((ck_def or {}).get("on_approved_spawn"), dict) else None,
                                "on_rejected_redo_node": (ck_def or {}).get("on_rejected_redo_node")
                                if isinstance((ck_def or {}).get("on_rejected_redo_node"), dict)
                                else None,
                                "requested_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
                            },
                        )
                except Exception:
                    checkpoint_id = None
            if checkpoint_id:
                payload["checkpoint_id"] = checkpoint_id
            await store.append_run_event(
                run_id=parent_id,
                event_type="join_ready",
                trace_id=parent.get("trace_id"),
                tenant_id=actor.get("tenant_id") or parent.get("tenant_id"),
                payload=payload,
            )
            return {
                "status": "ok",
                "run_id": parent_id,
                "join_id": str(join_id),
                "ready": True,
                "payload": payload,
                "checkpoint_id": checkpoint_id,
                "last_seq": last_seq,
            }

        await asyncio.sleep(0.5)

    # timeout
    return {
        "status": "timeout",
        "run_id": parent_id,
        "join_id": str(join_id),
        "ready": False,
        "last_seq": last_seq,
        "detail": {"missing": missing, "statuses": statuses},
    }

@router.post("/runs/{run_id}/nodes/{node_id}/redo")
async def redo_node(run_id: str, node_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-2 (node-level): Redo a single SOP node by re-spawning a new child run from stored request_payload.

    This is intentionally conservative:
    - Only invalidates downstream nodes that explicitly depend_on this node.
    - Does not auto-cancel already-running child runs; it marks them stale via run_events.

    Body:
      { "patch": {"input": {...}, "context": {...}}, "reason": "..." }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    parent_id = str(run_id)
    parent = await store.get_run_summary(run_id=parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="run_not_found")

    # RBAC (enforced): operator/admin only
    from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce

    actor = actor_from_http(http_request, request if isinstance(request, dict) else None)
    dec = rbac_check_permission(actor_role=actor.get("actor_role"), action="redo", resource_type="run")
    if not dec.allowed and rbac_should_enforce():
        deny = await rbac_guard(
            http_request=http_request,
            payload=request if isinstance(request, dict) else None,
            action="redo",
            resource_type="run",
            resource_id=parent_id,
            run_id=parent_id,
        )
        if deny:
            return deny

    body = dict(request or {}) if isinstance(request, dict) else {}
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else None
    reason = str(body.get("reason") or "node_redo")[:500]
    return await _redo_node_internal(store=store, parent=parent, parent_id=parent_id, node_id=str(node_id), actor=actor, patch=patch, reason=reason)


@router.post("/runs/{run_id}/checkpoints/request")
async def request_checkpoint(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-1: Request a human checkpoint (review) for an in-flight run.

    Body (suggested):
      {
        "node_id": "B->C",
        "title": "发布前审核",
        "artifact": {"type":"evidence_pack","id":"...","url":"..."},
        "risk_level": "high|medium|low",
        "suggested_reviewers": ["role:operator","user:u1"],
        "blocking": true
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="update", resource_type="run", resource_id=rid, run_id=rid)
    if deny:
        return deny

    from core.utils.ids import new_prefixed_id

    body = dict(request or {}) if isinstance(request, dict) else {}
    checkpoint_id = new_prefixed_id("ckpt")
    actor = actor_from_http(http_request, body)
    # optional checklist: explicit or derived from persona template id
    checklist = body.get("checklist") if isinstance(body.get("checklist"), list) else None
    if checklist is None:
        try:
            persona_tid = None
            if isinstance(body.get("persona_template_id"), str):
                persona_tid = str(body.get("persona_template_id")).strip()
            if not persona_tid and isinstance(body.get("context"), dict):
                pt = body.get("context", {}).get("persona_template_id")
                if isinstance(pt, str):
                    persona_tid = pt.strip()
            if persona_tid:
                checklist = await _persona_checklist_from_template(store=store, persona_template_id=persona_tid)
        except Exception:
            checklist = None
    payload = {
        "checkpoint_id": checkpoint_id,
        "node_id": body.get("node_id"),
        "title": body.get("title"),
        "artifact": body.get("artifact") if isinstance(body.get("artifact"), dict) else None,
        "risk_level": body.get("risk_level") or body.get("risk") or None,
        "suggested_reviewers": body.get("suggested_reviewers") if isinstance(body.get("suggested_reviewers"), list) else None,
        "blocking": bool(body.get("blocking", True)),
        "checklist": checklist if isinstance(checklist, list) else None,
        "requested_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
    }
    await store.append_run_event(
        run_id=rid,
        event_type="checkpoint_requested",
        trace_id=run.get("trace_id"),
        tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
        payload=payload,
    )
    return {"status": "ok", "run_id": rid, "checkpoint_id": checkpoint_id}


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/resolve")
async def resolve_checkpoint(run_id: str, checkpoint_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-1: Resolve a checkpoint (approve/reject/comment_only).
    This endpoint is event-based; it does not directly mutate run execution.

    Body (optional):
      {
        "decision": "approved|rejected|comment_only",
        "comments": "text",
        "checklist_result": [{"text":"...","status":"passed|failed","note":"..."}]
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="update", resource_type="run", resource_id=rid, run_id=rid)
    if deny:
        return deny
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    decision = str(body.get("decision") or body.get("status") or "approved").strip().lower()
    if decision not in {"approved", "rejected", "comment_only"}:
        raise HTTPException(status_code=400, detail="invalid_decision")
    checklist_result = body.get("checklist_result") if isinstance(body.get("checklist_result"), list) else None
    # normalize checklist_result
    norm = None
    if isinstance(checklist_result, list):
        out = []
        for it in checklist_result[:50]:
            if not isinstance(it, dict):
                continue
            st = str(it.get("status") or "").strip().lower()
            if st in {"pass", "passed", "ok", "true"}:
                st = "passed"
            elif st in {"fail", "failed", "no", "false"}:
                st = "failed"
            else:
                # ignore unknown statuses
                continue
            out.append({"text": str(it.get("text") or "")[:300], "status": st, "note": str(it.get("note") or "")[:500]})
        norm = out
    payload = {
        "checkpoint_id": str(checkpoint_id),
        "decision": decision,
        "comments": str(body.get("comments") or "")[:2000],
        "patch": body.get("patch") if isinstance(body.get("patch"), dict) else None,
        "checklist_result": norm,
        "resolved_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
    }
    await store.append_run_event(
        run_id=rid,
        event_type="checkpoint_resolved",
        trace_id=run.get("trace_id"),
        tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
        payload=payload,
    )
    return {"status": "ok", "run_id": rid, "checkpoint_id": str(checkpoint_id), "decision": decision}


def _merge_patch_into_payload(base_payload: Dict[str, Any], patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base_payload or {})
    p = patch if isinstance(patch, dict) else {}
    try:
        if isinstance(p.get("input"), dict):
            inp = out.get("input") if isinstance(out.get("input"), dict) else {}
            out["input"] = {**(inp or {}), **p.get("input")}
        if isinstance(p.get("context"), dict):
            ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
            out["context"] = {**(ctx or {}), **p.get("context")}
    except Exception:
        return out
    return out


async def _spawn_child_internal(
    *,
    store: Any,
    parent: Dict[str, Any],
    parent_id: str,
    actor: Dict[str, Any],
    node_id: Optional[str],
    depends_on: Optional[list],
    kind: str,
    target_id: str,
    payload: Dict[str, Any],
    trace_id: Optional[str] = None,
    extra_event_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from core.utils.ids import new_prefixed_id

    child_id = new_prefixed_id("run")
    tenant_id = actor.get("tenant_id") or parent.get("tenant_id")

    # Parent linkage
    try:
        pld = {
            "node_id": node_id,
            "depends_on": depends_on,
            "child_run_id": child_id,
            "kind": kind,
            "target_id": target_id,
            "requested_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
        }
        if isinstance(extra_event_payload, dict):
            pld.update(extra_event_payload)
        await store.append_run_event(
            run_id=parent_id,
            event_type="child_run_spawned",
            trace_id=parent.get("trace_id"),
            tenant_id=tenant_id,
            payload=pld,
        )
    except Exception:
        pass

    exec_req = ExecutionRequest(
        kind=kind,  # type: ignore[arg-type]
        target_id=str(target_id),
        payload=payload if isinstance(payload, dict) else {},
        user_id=str(actor.get("actor_id") or "system"),
        session_id=str(actor.get("actor_id") or "default"),
        run_id=str(child_id),
    )
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    resp["parent_run_id"] = parent_id
    resp["child_run_id"] = child_id
    resp["node_id"] = node_id

    # Child linkage
    try:
        await store.append_run_event(
            run_id=str(child_id),
            event_type="child_run_parent",
            trace_id=resp.get("trace_id") or trace_id,
            tenant_id=tenant_id,
            payload={"parent_run_id": parent_id, "node_id": node_id},
        )
    except Exception:
        pass
    return resp


async def _redo_node_internal(
    *,
    store: Any,
    parent: Dict[str, Any],
    parent_id: str,
    node_id: str,
    actor: Dict[str, Any],
    patch: Optional[Dict[str, Any]],
    reason: str,
) -> Dict[str, Any]:
    """
    P6-2: internal helper used by node redo endpoint and checkpoint apply.
    """
    # Find latest child_run_spawned for this node_id
    ev = await store.list_run_events(run_id=parent_id, after_seq=0, limit=2000)
    items = ev.get("items") or []
    latest = None
    for e in reversed(items):
        if e.get("type") != "child_run_spawned":
            continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if str(p.get("node_id") or "") == str(node_id):
            latest = p
            break
    if not isinstance(latest, dict):
        raise HTTPException(status_code=404, detail="node_not_found")

    kind = str(latest.get("kind") or "").strip().lower()
    target_id = str(latest.get("target_id") or "").strip()
    base_payload = latest.get("request_payload") if isinstance(latest.get("request_payload"), dict) else {}
    base_payload = dict(base_payload or {}) if isinstance(base_payload, dict) else {}
    if kind not in {"agent", "skill", "tool", "graph"} or not target_id:
        raise HTTPException(status_code=409, detail="node_redo_not_supported")

    base_payload = _merge_patch_into_payload(base_payload, patch)
    supersedes_child_run_id = str(latest.get("child_run_id") or "").strip() or None

    def _redact(obj: Any, *, max_str: int = 2000, max_items: int = 60, depth: int = 0) -> Any:
        # allow moderately deep nested context (e.g., review_feedback.failed_items)
        if depth > 8:
            return "<truncated>"
        if obj is None:
            return None
        if isinstance(obj, (int, float, bool)):
            return obj
        if isinstance(obj, str):
            s = obj
            return s if len(s) <= max_str else (s[:max_str] + "…")
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for i, (k, v) in enumerate(list(obj.items())[:max_items]):
                kk = str(k)
                if kk.lower() in {"raw", "content_raw", "binary", "bytes"}:
                    out[kk] = "<redacted>"
                    continue
                out[kk] = _redact(v, max_str=max_str, max_items=max_items, depth=depth + 1)
            if len(obj) > max_items:
                out["__truncated__"] = True
            return out
        if isinstance(obj, list):
            out = [_redact(x, max_str=max_str, max_items=max_items, depth=depth + 1) for x in obj[:max_items]]
            if len(obj) > max_items:
                out.append("<truncated>")
            return out
        return str(obj)

    from core.utils.ids import new_prefixed_id

    new_child_id = new_prefixed_id("run")
    tenant_id = actor.get("tenant_id") or parent.get("tenant_id")

    # Record redo request
    try:
        await store.append_run_event(
            run_id=parent_id,
            event_type="node_redo_requested",
            trace_id=parent.get("trace_id"),
            tenant_id=tenant_id,
            payload={"node_id": str(node_id), "new_child_run_id": new_child_id, "reason": reason},
        )
    except Exception:
        pass

    exec_req = ExecutionRequest(
        kind=kind,  # type: ignore[arg-type]
        target_id=str(target_id),
        payload=base_payload,
        user_id=str(actor.get("actor_id") or "system"),
        session_id=str(actor.get("actor_id") or "default"),
        run_id=str(new_child_id),
    )
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    resp["parent_run_id"] = parent_id
    resp["node_id"] = str(node_id)
    resp["child_run_id"] = str(new_child_id)
    resp["supersedes_child_run_id"] = supersedes_child_run_id

    # Link events
    try:
        await store.append_run_event(
            run_id=parent_id,
            event_type="child_run_spawned",
            trace_id=parent.get("trace_id"),
            tenant_id=tenant_id,
            payload={
                "node_id": str(node_id),
                "child_run_id": str(new_child_id),
                "kind": kind,
                "target_id": target_id,
                "supersedes_child_run_id": latest.get("child_run_id"),
                "reason": reason,
                "request_payload": _redact(base_payload if isinstance(base_payload, dict) else {}),
                "request_payload_redacted": True,
            },
        )
    except Exception:
        pass
    try:
        await store.append_run_event(
            run_id=str(new_child_id),
            event_type="child_run_parent",
            trace_id=resp.get("trace_id"),
            tenant_id=tenant_id,
            payload={"parent_run_id": parent_id, "node_id": str(node_id)},
        )
    except Exception:
        pass

    # Invalidate downstream nodes that depend_on this node
    invalidated = []
    try:
        for e in items:
            if e.get("type") != "child_run_spawned":
                continue
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            dn = p.get("depends_on") if isinstance(p.get("depends_on"), list) else []
            if str(node_id) in [str(x) for x in dn]:
                dn_node = p.get("node_id")
                dn_child = p.get("child_run_id")
                if dn_node and dn_child:
                    invalidated.append({"node_id": dn_node, "child_run_id": dn_child})
                    try:
                        await store.append_run_event(
                            run_id=parent_id,
                            event_type="node_invalidated",
                            trace_id=parent.get("trace_id"),
                            tenant_id=tenant_id,
                            payload={"node_id": dn_node, "child_run_id": dn_child, "because": str(node_id), "reason": "upstream_redo"},
                        )
                    except Exception:
                        pass
                    try:
                        await store.append_run_event(
                            run_id=str(dn_child),
                            event_type="stale",
                            trace_id=None,
                            tenant_id=tenant_id,
                            payload={"because_node": str(node_id), "parent_run_id": parent_id, "reason": "upstream_redo"},
                        )
                    except Exception:
                        pass
    except Exception:
        invalidated = invalidated
    resp["invalidated"] = invalidated
    return resp


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/apply")
async def apply_checkpoint(run_id: str, checkpoint_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-4 enhancement: Apply a resolved checkpoint to advance workflow.

    Current supported action:
    - If checkpoint was approved AND checkpoint_requested payload contains `on_approved_spawn`,
      spawn the described child run.

    Idempotency:
    - If checkpoint_applied already exists for checkpoint_id, this is a no-op.

    Body:
      { "patch": {"input": {...}, "context": {...}}, "reason": "..." }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="update", resource_type="run", resource_id=rid, run_id=rid)
    if deny:
        return deny

    # Load events
    ev = await store.list_run_events(run_id=rid, after_seq=0, limit=3000)
    items = ev.get("items") or []

    # Idempotency check
    for e in reversed(items):
        if e.get("type") == "checkpoint_applied":
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if str(p.get("checkpoint_id") or "") == str(checkpoint_id):
                return {"status": "already_applied", "run_id": rid, "checkpoint_id": str(checkpoint_id), "payload": p}

    requested = None
    resolved = None
    resolved_event = None
    for e in reversed(items):
        if e.get("type") == "checkpoint_resolved":
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if str(p.get("checkpoint_id") or "") == str(checkpoint_id):
                resolved = p
                resolved_event = e
                break
    for e in reversed(items):
        if e.get("type") == "checkpoint_requested":
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if str(p.get("checkpoint_id") or "") == str(checkpoint_id):
                requested = p
                break

    if not resolved:
        raise HTTPException(status_code=409, detail="checkpoint_not_resolved")
    if not requested:
        raise HTTPException(status_code=404, detail="checkpoint_not_found")

    actor = actor_from_http(http_request, request if isinstance(request, dict) else None)
    decision = str(resolved.get("decision") or "").strip().lower()
    if decision != "approved":
        # Rejected branch can optionally trigger a node redo (auto-fix loop).
        if decision == "rejected":
            redo_cfg = requested.get("on_rejected_redo_node") if isinstance(requested.get("on_rejected_redo_node"), dict) else None
            if isinstance(redo_cfg, dict) and str(redo_cfg.get("node_id") or "").strip():
                # RBAC (enforced): redo requires operator/admin
                from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce

                dec = rbac_check_permission(actor_role=actor.get("actor_role"), action="redo", resource_type="run")
                if not dec.allowed and rbac_should_enforce():
                    deny = await rbac_guard(
                        http_request=http_request,
                        payload=request if isinstance(request, dict) else None,
                        action="redo",
                        resource_type="run",
                        resource_id=rid,
                        run_id=rid,
                    )
                    if deny:
                        return deny

                body = dict(request or {}) if isinstance(request, dict) else {}
                patch0 = redo_cfg.get("patch") if isinstance(redo_cfg.get("patch"), dict) else None
                # If config doesn't provide patch, allow request.patch to override.
                patch1 = patch0 or (body.get("patch") if isinstance(body.get("patch"), dict) else None)
                # If still no patch: derive review feedback from checklist_result/comments into context.review_feedback
                if patch1 is None:
                    try:
                        failed = []
                        cr = resolved.get("checklist_result") if isinstance(resolved.get("checklist_result"), list) else []
                        for it in cr[:50]:
                            if not isinstance(it, dict):
                                continue
                            st = str(it.get("status") or "").strip().lower()
                            # include any non-passed items as failure context
                            if st != "passed":
                                failed.append(
                                    {
                                        "text": str(it.get("text") or "")[:300],
                                        "note": str(it.get("note") or "")[:500],
                                        "status": st or "unknown",
                                    }
                                )
                        patch1 = {
                            "context": {
                                "review_feedback": {
                                    "checkpoint_id": str(checkpoint_id),
                                    "decision": "rejected",
                                    "comments": str(resolved.get("comments") or "")[:2000],
                                    "failed_items": failed[:20],
                                }
                            }
                        }
                    except Exception:
                        patch1 = None
                reason = str(body.get("reason") or redo_cfg.get("reason") or "checkpoint_rejected_redo")[:500]
                redo_resp = await _redo_node_internal(
                    store=store,
                    parent=run,
                    parent_id=rid,
                    node_id=str(redo_cfg.get("node_id")).strip(),
                    actor=actor,
                    patch=patch1,
                    reason=reason,
                )
                # Follow-up checkpoint: re-verify failed items (best-effort, idempotent via checkpoint_applied guard).
                followup_checkpoint_id = None
                try:
                    from core.utils.ids import new_prefixed_id

                    failed_items = []
                    fb = None
                    try:
                        fb = ((patch1 or {}).get("context") or {}).get("review_feedback") if isinstance(patch1, dict) else None
                    except Exception:
                        fb = None
                    if isinstance(fb, dict):
                        failed_items = fb.get("failed_items") if isinstance(fb.get("failed_items"), list) else []
                    checklist2 = []
                    for it0 in failed_items[:20]:
                        if not isinstance(it0, dict):
                            continue
                        txt = str(it0.get("text") or "").strip()
                        if txt:
                            checklist2.append({"text": txt[:300], "status": "pending"})
                    # only create follow-up if there is something concrete to verify
                    if checklist2:
                        followup_checkpoint_id = new_prefixed_id("ckpt")
                        # Evidence pack: summarize redo run + syscalls so reviewers don't need to dig logs.
                        evidence_pack = {}
                        try:
                            redo_run_id = str(redo_resp.get("child_run_id") or "")
                            prev_run_id = str(redo_resp.get("supersedes_child_run_id") or "")
                            redo_sum = await store.get_run_summary(run_id=redo_run_id) if redo_run_id else None
                            prev_sum = await store.get_run_summary(run_id=prev_run_id) if prev_run_id else None
                            syscalls = await store.list_syscall_events(run_id=redo_run_id, limit=50, offset=0) if redo_run_id else {"items": []}
                            evidence_pack = {
                                "redo_run": {
                                    "run_id": redo_run_id,
                                    "status": (redo_sum or {}).get("status") if isinstance(redo_sum, dict) else None,
                                    "target_type": (redo_sum or {}).get("target_type") if isinstance(redo_sum, dict) else None,
                                    "target_id": (redo_sum or {}).get("target_id") if isinstance(redo_sum, dict) else None,
                                    "error_code": (redo_sum or {}).get("error_code") if isinstance(redo_sum, dict) else None,
                                    "output_summary": _summarize_output((redo_sum or {}).get("output") if isinstance(redo_sum, dict) else None),
                                },
                                "prev_run": {
                                    "run_id": prev_run_id or None,
                                    "status": (prev_sum or {}).get("status") if isinstance(prev_sum, dict) else None,
                                    "target_type": (prev_sum or {}).get("target_type") if isinstance(prev_sum, dict) else None,
                                    "target_id": (prev_sum or {}).get("target_id") if isinstance(prev_sum, dict) else None,
                                    "error_code": (prev_sum or {}).get("error_code") if isinstance(prev_sum, dict) else None,
                                    "output_summary": _summarize_output((prev_sum or {}).get("output") if isinstance(prev_sum, dict) else None),
                                },
                                "invalidated": redo_resp.get("invalidated"),
                                "syscalls": _summarize_syscalls((syscalls or {}).get("items") if isinstance(syscalls, dict) else []),
                                "diff": {
                                    "prev_run_id": prev_run_id or None,
                                    "redo_run_id": redo_run_id,
                                    "status_changed": (
                                        (prev_sum or {}).get("status") != (redo_sum or {}).get("status")
                                        if isinstance(prev_sum, dict) and isinstance(redo_sum, dict)
                                        else None
                                    ),
                                    "error_code_changed": (
                                        (prev_sum or {}).get("error_code") != (redo_sum or {}).get("error_code")
                                        if isinstance(prev_sum, dict) and isinstance(redo_sum, dict)
                                        else None
                                    ),
                                    "output_diff": _diff_outputs(
                                        (prev_sum or {}).get("output") if isinstance(prev_sum, dict) else None,
                                        (redo_sum or {}).get("output") if isinstance(redo_sum, dict) else None,
                                    ),
                                },
                            }
                        except Exception:
                            evidence_pack = {}
                        await store.append_run_event(
                            run_id=rid,
                            event_type="checkpoint_requested",
                            trace_id=run.get("trace_id"),
                            tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
                            payload={
                                "checkpoint_id": followup_checkpoint_id,
                                "node_id": f"redo:{str(redo_cfg.get('node_id')).strip()}",
                                "title": "修复后复核",
                                "artifact": {
                                    "type": "redo_result",
                                    "from_checkpoint_id": str(checkpoint_id),
                                    "redo_node_id": str(redo_cfg.get("node_id")).strip(),
                                    "redo_child_run_id": redo_resp.get("child_run_id"),
                                    "review_feedback": ((patch1 or {}).get("context") or {}).get("review_feedback") if isinstance(patch1, dict) else None,
                                    "evidence_pack": evidence_pack,
                                },
                                "risk_level": str(requested.get("risk_level") or "medium"),
                                "blocking": True,
                                "previous_checkpoint_id": str(checkpoint_id),
                                "checklist": checklist2,
                                "requested_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
                            },
                        )
                except Exception:
                    followup_checkpoint_id = None
                await store.append_run_event(
                    run_id=rid,
                    event_type="checkpoint_applied",
                    trace_id=run.get("trace_id"),
                    tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
                    payload={
                        "checkpoint_id": str(checkpoint_id),
                        "decision": decision,
                        "action": "redo_node",
                        "node_id": str(redo_cfg.get("node_id")).strip(),
                        "child_run_id": redo_resp.get("child_run_id"),
                        "invalidated": redo_resp.get("invalidated"),
                        "followup_checkpoint_id": followup_checkpoint_id,
                    },
                )
                return {
                    "status": "ok",
                    "run_id": rid,
                    "checkpoint_id": str(checkpoint_id),
                    "action": "redo_node",
                    "redo": redo_resp,
                    "followup_checkpoint_id": followup_checkpoint_id,
                }

        await store.append_run_event(
            run_id=rid,
            event_type="checkpoint_applied",
            trace_id=run.get("trace_id"),
            tenant_id=run.get("tenant_id"),
            payload={"checkpoint_id": str(checkpoint_id), "decision": decision, "action": "noop"},
        )
        return {"status": "noop", "run_id": rid, "checkpoint_id": str(checkpoint_id), "decision": decision}

    spawn = requested.get("on_approved_spawn") if isinstance(requested.get("on_approved_spawn"), dict) else None
    if not isinstance(spawn, dict):
        await store.append_run_event(
            run_id=rid,
            event_type="checkpoint_applied",
            trace_id=run.get("trace_id"),
            tenant_id=run.get("tenant_id"),
            payload={"checkpoint_id": str(checkpoint_id), "decision": decision, "action": "noop_no_spawn"},
        )
        return {"status": "noop", "run_id": rid, "checkpoint_id": str(checkpoint_id), "decision": decision, "reason": "no_on_approved_spawn"}

    node_id = str(spawn.get("node_id") or "").strip() or None
    kind = str(spawn.get("kind") or "").strip().lower()
    target_id = str(spawn.get("target_id") or "").strip()
    payload0 = spawn.get("payload") if isinstance(spawn.get("payload"), dict) else {}
    depends_on = spawn.get("depends_on") if isinstance(spawn.get("depends_on"), list) else None
    depends_on = [str(x).strip() for x in (depends_on or []) if str(x).strip()] or None
    if kind not in {"agent", "skill", "tool", "graph"} or not target_id:
        raise HTTPException(status_code=400, detail="invalid_spawn")

    body = dict(request or {}) if isinstance(request, dict) else {}
    payload2 = _merge_patch_into_payload(dict(payload0 or {}), body.get("patch") if isinstance(body.get("patch"), dict) else None)
    reason = str(body.get("reason") or "checkpoint_apply")[:500]

    child_resp = await _spawn_child_internal(
        store=store,
        parent=run,
        parent_id=rid,
        actor=actor,
        node_id=node_id,
        depends_on=depends_on,
        kind=kind,
        target_id=target_id,
        payload=payload2,
        extra_event_payload={"triggered_by": {"checkpoint_id": str(checkpoint_id), "reason": reason}},
    )
    await store.append_run_event(
        run_id=rid,
        event_type="checkpoint_applied",
        trace_id=run.get("trace_id"),
        tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
        payload={
            "checkpoint_id": str(checkpoint_id),
            "decision": decision,
            "action": "spawn",
            "child_run_id": child_resp.get("child_run_id"),
            "node_id": node_id,
            "kind": kind,
            "target_id": target_id,
        },
    )
    return {"status": "ok", "run_id": rid, "checkpoint_id": str(checkpoint_id), "action": "spawn", "child": child_resp}


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/redo")
async def redo_from_checkpoint(run_id: str, checkpoint_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P6-2: Reject -> redo.
    Create a new run by replaying run_start.request_payload, with optional patch overrides.

    Body:
      {
        "patch": {"input": {...}, "context": {...}},
        "reason": "why redo"
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    # RBAC (enforced mode): only operator/admin can redo
    from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce

    actor = actor_from_http(http_request, request if isinstance(request, dict) else None)
    dec = rbac_check_permission(actor_role=actor.get("actor_role"), action="redo", resource_type="run")
    if not dec.allowed and rbac_should_enforce():
        deny = await rbac_guard(
            http_request=http_request,
            payload=request if isinstance(request, dict) else None,
            action="redo",
            resource_type="run",
            resource_id=rid,
            run_id=rid,
        )
        if deny:
            return deny

    start = await store.get_run_start_event(run_id=rid)
    if not start:
        raise HTTPException(status_code=404, detail="run_start_not_found")
    payload0 = start.get("payload") if isinstance(start, dict) else {}
    payload0 = payload0 if isinstance(payload0, dict) else {}
    kind = str(payload0.get("kind") or "").strip()
    req_payload = payload0.get("request_payload") if isinstance(payload0.get("request_payload"), dict) else {}
    req_payload = dict(req_payload or {}) if isinstance(req_payload, dict) else {}

    # Apply patch (best-effort shallow merge for input/context)
    body = dict(request or {}) if isinstance(request, dict) else {}
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    try:
        if isinstance(patch, dict) and isinstance(req_payload, dict):
            if isinstance(patch.get("input"), dict):
                inp = req_payload.get("input") if isinstance(req_payload.get("input"), dict) else {}
                req_payload["input"] = {**(inp or {}), **patch.get("input")}
            if isinstance(patch.get("context"), dict):
                ctx = req_payload.get("context") if isinstance(req_payload.get("context"), dict) else {}
                req_payload["context"] = {**(ctx or {}), **patch.get("context")}
    except Exception:
        pass

    # Determine target_id
    target_id = None
    if kind == "agent":
        target_id = payload0.get("agent_id")
    elif kind == "skill":
        target_id = payload0.get("skill_id")
    elif kind == "tool":
        target_id = payload0.get("tool_name")
    elif kind == "graph":
        target_id = payload0.get("graph_name") or payload0.get("target_id")
    if not kind or not target_id:
        raise HTTPException(status_code=409, detail="redo_not_supported")

    from core.utils.ids import new_prefixed_id

    new_id = new_prefixed_id("run")
    reason = str(body.get("reason") or "checkpoint_redo")[:500]

    # Emit linkage event on original run
    try:
        await store.append_run_event(
            run_id=rid,
            event_type="checkpoint_redo_requested",
            trace_id=run.get("trace_id"),
            tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
            payload={"checkpoint_id": str(checkpoint_id), "new_run_id": new_id, "reason": reason},
        )
    except Exception:
        pass

    exec_req = ExecutionRequest(
        kind=kind,  # type: ignore[arg-type]
        target_id=str(target_id),
        payload=req_payload,
        user_id=str(payload0.get("user_id") or actor.get("actor_id") or "system"),
        session_id=str(payload0.get("session_id") or "default"),
        run_id=new_id,
    )
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    resp["previous_run_id"] = rid
    resp["new_run_id"] = new_id
    resp["checkpoint_id"] = str(checkpoint_id)

    # Emit linkage event on new run
    try:
        await store.append_run_event(
            run_id=new_id,
            event_type="checkpoint_redo_from",
            trace_id=resp.get("trace_id"),
            tenant_id=actor.get("tenant_id") or run.get("tenant_id"),
            payload={"from_run_id": rid, "checkpoint_id": str(checkpoint_id), "reason": reason},
        )
    except Exception:
        pass

    return resp


@router.post("/runs/{run_id}/evaluate")
async def submit_run_evaluation(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    P1 Evaluator Workbench:
    - Accept a structured evaluator report JSON
    - Apply threshold gate
    - Persist as learning artifact + run event + audit log

    Note: This endpoint is intentionally "report-first" (LLM-agnostic). You can generate the
    report using any evaluator agent and then submit it here.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    deny = await rbac_guard(http_request=http_request, payload=request or {}, action="update", resource_type="run", resource_id=rid)
    if deny:
        return deny

    body = dict(request or {}) if isinstance(request, dict) else {}
    evaluator = str((body or {}).get("evaluator") or "evaluator").strip()
    report = (body or {}).get("report")
    thresholds0 = (body or {}).get("thresholds") if isinstance((body or {}).get("thresholds"), dict) else {}
    enforce_gate = bool((body or {}).get("enforce_gate", False))
    project_id = str((body or {}).get("project_id") or "").strip() or None
    url = str((body or {}).get("url") or "").strip() or None
    tag_template = str((body or {}).get("tag_template") or "").strip() or None
    base_evidence_pack_id_req = str((body or {}).get("base_evidence_pack_id") or "").strip() or None
    if not isinstance(report, dict):
        raise HTTPException(status_code=400, detail="missing_report")

    from core.harness.evaluation.workbench import EvaluatorThresholds, apply_threshold_gate, persist_evaluation, validate_report

    ok, reason = validate_report(report)
    if not ok:
        raise HTTPException(status_code=400, detail=f"invalid_report:{reason}")
    thresholds = EvaluatorThresholds.from_dict(thresholds0)
    gated_report = apply_threshold_gate(report, thresholds)
    # Stamp identity for baseline search / audit
    try:
        if isinstance(gated_report, dict) and project_id:
            gated_report.setdefault("project_id", project_id)
        if isinstance(gated_report, dict) and url:
            gated_report.setdefault("url", url)
        if isinstance(gated_report, dict) and base_evidence_pack_id_req:
            gated_report.setdefault("base_evidence_pack_id", base_evidence_pack_id_req)
    except Exception:
        pass
    actor = actor_from_http(http_request, body or {})
    saved = await persist_evaluation(
        execution_store=store,
        run_id=rid,
        trace_id=run.get("trace_id"),
        evaluator=evaluator,
        report=gated_report,
        thresholds=thresholds,
        actor=actor,
        metadata_extra={"project_id": project_id, "url": url, "tag_template": tag_template},
    )
    # Update run_state (best-effort) from evaluator report
    try:
        from core.harness.restatement.run_state import merge_from_evaluation, normalize_run_state
        from core.learning.manager import LearningManager
        from core.learning.types import LearningArtifactKind

        mgr = LearningManager(execution_store=store)
        # read latest run_state
        latest = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="run_state", limit=10, offset=0)
        items = latest.get("items") if isinstance(latest, dict) else None
        cur = {}
        if isinstance(items, list) and items:
            items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
            cur = (items2[0] or {}).get("payload") if isinstance(items2[0], dict) else {}
        cur2 = normalize_run_state(cur, run_id=rid)
        # Ensure task stays visible
        if not str(cur2.get("task") or "").strip():
            cur2["task"] = str(run.get("task") or "")
        merged = merge_from_evaluation(cur2, evaluation_report=gated_report, source="evaluator")
        await mgr.create_artifact(
            kind=LearningArtifactKind.RUN_STATE,
            target_type="run",
            target_id=rid,
            version=f"run_state:{int(time.time())}",
            status="draft",
            payload=merged,
            metadata={"source": "evaluator", "locked": bool(merged.get("locked"))},
            trace_id=run.get("trace_id"),
            run_id=rid,
        )
    except Exception:
        pass
    if enforce_gate and not bool(gated_report.get("pass")):
        raise HTTPException(status_code=409, detail={"code": "evaluation_failed", "artifact_id": saved.get("artifact_id"), "report": gated_report})
    return {"status": "ok", "artifact_id": saved.get("artifact_id"), "report": gated_report}


@router.get("/runs/{run_id}/evaluation/latest")
async def get_latest_run_evaluation(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(
        target_type="run",
        target_id=rid,
        kind="evaluation_report",
        limit=20,
        offset=0,
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.get("/runs/{run_id}/investigate/latest")
async def get_latest_investigate_report(run_id: str, rt: RuntimeDep = None):
    """Latest investigate_report artifact for this run (best-effort)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    res = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="investigate_report", limit=20, offset=0)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.post("/runs/{run_id}/investigate/auto")
async def auto_investigate_run(run_id: str, http_request: Request, rt: RuntimeDep = None):
    """
    P1-2: One-click investigate report.
    Aggregates: run summary + latest eval/evidence + syscall signals into a single artifact.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    deny = await rbac_guard(http_request=http_request, payload={"run_id": rid}, action="read", resource_type="run", resource_id=rid)
    if deny:
        return deny

    trace_id = run.get("trace_id")

    def _latest(items: Any) -> Any:
        if isinstance(items, list) and items:
            return sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)[0]
        return None

    latest_eval = None
    latest_pack = None
    latest_diff = None
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evaluation_report", limit=10, offset=0)
        latest_eval = _latest((r0 or {}).get("items"))
    except Exception:
        latest_eval = None
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_pack", limit=10, offset=0)
        latest_pack = _latest((r0 or {}).get("items"))
    except Exception:
        latest_pack = None
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_diff", limit=10, offset=0)
        latest_diff = _latest((r0 or {}).get("items"))
    except Exception:
        latest_diff = None

    # syscall signals (best-effort)
    syscall_items: list = []
    syscall_summary: Dict[str, Any] = {"total": 0, "errors": 0, "top_errors": [], "slow": []}
    try:
        s0 = await store.list_syscall_events(run_id=rid, limit=200, offset=0)
        syscall_items = (s0 or {}).get("items") if isinstance(s0, dict) else []
        if not isinstance(syscall_items, list):
            syscall_items = []
        errs = [x for x in syscall_items if str((x or {}).get("status") or "").lower() not in {"ok", "success"} or (x or {}).get("error")]
        counts: Dict[str, int] = {}
        for e in errs:
            code = str((e or {}).get("error_code") or (e or {}).get("error") or "error").strip()
            counts[code] = counts.get(code, 0) + 1
        top_errors = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        slow = sorted(syscall_items, key=lambda x: float((x or {}).get("duration_ms") or 0), reverse=True)[:10]
        syscall_summary = {
            "total": len(syscall_items),
            "errors": len(errs),
            "top_errors": [{"error_code": k, "count": v} for k, v in top_errors],
            "slow": [
                {
                    "name": (x or {}).get("name"),
                    "kind": (x or {}).get("kind"),
                    "status": (x or {}).get("status"),
                    "duration_ms": (x or {}).get("duration_ms"),
                    "error_code": (x or {}).get("error_code"),
                }
                for x in slow
            ],
        }
    except Exception:
        syscall_items = []

    eval_payload = (latest_eval or {}).get("payload") if isinstance(latest_eval, dict) else {}
    pack_payload = (latest_pack or {}).get("payload") if isinstance(latest_pack, dict) else {}
    diff_payload = (latest_diff or {}).get("payload") if isinstance(latest_diff, dict) else {}
    coverage = (pack_payload or {}).get("coverage") if isinstance(pack_payload, dict) else {}
    assertions = (eval_payload or {}).get("assertions") if isinstance(eval_payload, dict) else {}
    issues = (eval_payload or {}).get("issues") if isinstance(eval_payload, dict) else None
    if not isinstance(issues, list):
        issues = []

    syscall_sample = []
    for x in syscall_items[:50]:
        syscall_sample.append(
            {
                "id": (x or {}).get("id"),
                "kind": (x or {}).get("kind"),
                "name": (x or {}).get("name"),
                "status": (x or {}).get("status"),
                "duration_ms": (x or {}).get("duration_ms"),
                "error_code": (x or {}).get("error_code"),
                "error": (x or {}).get("error"),
            }
        )

    payload = {
        "schema_version": "0.1",
        "run": {
            "run_id": rid,
            "trace_id": trace_id,
            "status": run.get("status"),
            "task": run.get("task"),
            "start_time": run.get("start_time"),
            "end_time": run.get("end_time"),
        },
        "links": {
            "evaluation_report_id": (latest_eval or {}).get("artifact_id") if isinstance(latest_eval, dict) else None,
            "evidence_pack_id": (latest_pack or {}).get("artifact_id") if isinstance(latest_pack, dict) else None,
            "evidence_diff_id": (latest_diff or {}).get("artifact_id") if isinstance(latest_diff, dict) else None,
        },
        "evaluation": {
            "pass": (eval_payload or {}).get("pass") if isinstance(eval_payload, dict) else None,
            "score": (eval_payload or {}).get("score") if isinstance(eval_payload, dict) else None,
            "regression": (eval_payload or {}).get("regression") if isinstance(eval_payload, dict) else None,
            "issues_count": len(issues),
            "issues_top": issues[:10],
        },
        "evidence": {
            "url": (pack_payload or {}).get("url") if isinstance(pack_payload, dict) else None,
            "coverage": coverage if isinstance(coverage, dict) else {},
            "diff_metrics": (diff_payload or {}).get("metrics") if isinstance(diff_payload, dict) else None,
            "diff_summary": (diff_payload or {}).get("summary") if isinstance(diff_payload, dict) else None,
        },
        "assertions": assertions if isinstance(assertions, dict) else {},
        "syscalls": {"summary": syscall_summary, "sample": syscall_sample},
    }

    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.INVESTIGATE_REPORT,
        target_type="run",
        target_id=rid,
        version=f"investigate:{int(time.time())}",
        status="draft",
        payload=payload,
        metadata={"source": "auto_investigate"},
        trace_id=str(trace_id) if trace_id else None,
        run_id=rid,
    )
    return {"status": "ok", "artifact_id": art.artifact_id, "report": payload}


@router.get("/runs/{run_id}/state/latest")
async def get_latest_run_state(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(
        target_type="run",
        target_id=rid,
        kind="run_state",
        limit=20,
        offset=0,
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        from core.harness.restatement.run_state import default_run_state

        return {"status": "ok", "item": {"payload": default_run_state(run_id=rid, task=str(run.get("task") or "")), "artifact_id": None}}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.get("/runs/{run_id}/evidence_pack/latest")
async def get_latest_evidence_pack(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_pack", limit=20, offset=0)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.post("/runs/{run_id}/evidence/diff")
async def compute_run_evidence_diff(run_id: str, request: EvidenceDiffRequest, http_request: Request, rt: RuntimeDep = None):
    """
    Compute & persist evidence diff between two evidence_pack artifacts.
    Body: { "base_evidence_pack_id": "...", "new_evidence_pack_id": "..." }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    body = request.dict(exclude_none=True) if hasattr(request, "dict") else {}
    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="run", resource_id=rid)
    if deny:
        return deny
    base_id = str((body or {}).get("base_evidence_pack_id") or "").strip()
    new_id = str((body or {}).get("new_evidence_pack_id") or "").strip()
    if not base_id or not new_id:
        raise HTTPException(status_code=400, detail="missing_evidence_pack_ids")
    base_art = await store.get_learning_artifact(artifact_id=base_id)
    new_art = await store.get_learning_artifact(artifact_id=new_id)
    if not base_art or not new_art:
        raise HTTPException(status_code=404, detail="evidence_pack_not_found")
    base_payload = base_art.get("payload") if isinstance(base_art, dict) else None
    new_payload = new_art.get("payload") if isinstance(new_art, dict) else None
    if not isinstance(base_payload, dict) or not isinstance(new_payload, dict):
        raise HTTPException(status_code=400, detail="invalid_evidence_pack_payload")
    base_payload = dict(base_payload)
    new_payload = dict(new_payload)
    base_payload["evidence_pack_id"] = base_id
    new_payload["evidence_pack_id"] = new_id
    from core.harness.evaluation.evidence_diff import compute_evidence_diff
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    diff = compute_evidence_diff(base_payload, new_payload)
    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.EVIDENCE_DIFF,
        target_type="run",
        target_id=rid,
        version=f"evidence_diff:{int(time.time())}",
        status="draft",
        payload=diff,
        metadata={"source": "manual", "base_evidence_pack_id": base_id, "new_evidence_pack_id": new_id},
        trace_id=run.get("trace_id"),
        run_id=rid,
    )
    return {"status": "ok", "artifact_id": art.artifact_id, "diff": diff}


@router.post("/runs/{run_id}/state")
async def upsert_run_state(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Manual run_state upsert (human-in-the-loop).
    Body:
      { "state": {...}, "lock": true|false }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    deny = await rbac_guard(http_request=http_request, payload=request or {}, action="update", resource_type="run", resource_id=rid)
    if deny:
        return deny

    st = (request or {}).get("state")
    if not isinstance(st, dict):
        raise HTTPException(status_code=400, detail="missing_state")
    lock_flag = (request or {}).get("lock")
    from core.harness.restatement.run_state import normalize_run_state
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    actor = actor_from_http(http_request, request or {})
    norm = normalize_run_state(st, run_id=rid)
    if lock_flag is not None:
        norm["locked"] = bool(lock_flag)
    norm["updated_by"] = {"source": "manual", "actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")}
    norm["updated_at"] = time.time()

    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.RUN_STATE,
        target_type="run",
        target_id=rid,
        version=f"run_state:{int(time.time())}",
        status="draft",
        payload=norm,
        metadata={"source": "manual", "locked": bool(norm.get("locked"))},
        trace_id=run.get("trace_id"),
        run_id=rid,
    )
    try:
        await store.append_run_event(
            run_id=rid,
            event_type="run_state",
            trace_id=run.get("trace_id"),
            tenant_id=actor.get("tenant_id"),
            payload={"artifact_id": art.artifact_id, "locked": bool(norm.get("locked")), "source": "manual"},
        )
    except Exception:
        pass
    return {"status": "ok", "artifact_id": art.artifact_id, "state": norm}


@router.post("/runs/{run_id}/evaluate/auto")
async def auto_run_evaluation(run_id: str, request: AutoEvalRequest, http_request: Request, rt: RuntimeDep = None):
    """
    P1: One-click auto evaluation.

    Uses an LLM to generate a structured evaluation report from run summary + run_events,
    then persists it via the evaluator workbench (learning artifact + run event).
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    body = request.dict(exclude_none=True) if hasattr(request, "dict") else {}
    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="run", resource_id=rid)
    if deny:
        return deny

    # Load limited events as evidence
    try:
        ev = await store.list_run_events(run_id=rid, after_seq=0, limit=200)
        events = ev.get("items") or []
    except Exception:
        events = []

    evaluator = str((body or {}).get("evaluator") or "auto-llm").strip()
    thresholds0 = (body or {}).get("thresholds") if isinstance((body or {}).get("thresholds"), dict) else {}
    enforce_gate = bool((body or {}).get("enforce_gate", False))
    extra = (body or {}).get("extra") if isinstance((body or {}).get("extra"), dict) else {}
    policy_override = (body or {}).get("policy") if isinstance((body or {}).get("policy"), dict) else None
    project_id = str((body or {}).get("project_id") or "").strip() or None
    url = str((body or {}).get("url") or "").strip() or None
    steps = (body or {}).get("steps") if isinstance((body or {}).get("steps"), list) else None
    expected_tags = (body or {}).get("expected_tags") if isinstance((body or {}).get("expected_tags"), list) else None
    tag_expectations = (body or {}).get("tag_expectations") if isinstance((body or {}).get("tag_expectations"), dict) else None
    tag_template = str((body or {}).get("tag_template") or "").strip() or None
    base_evidence_pack_id_req = str((body or {}).get("base_evidence_pack_id") or "").strip() or None

    # Load evaluation policy (global default) unless caller overrides.
    try:
        from core.harness.evaluation.policy import DEFAULT_POLICY, EvaluationPolicy, merge_policy

        # system/default
        sys_obj = DEFAULT_POLICY
        try:
            sys_res = await store.list_learning_artifacts(target_type="system", target_id="default", kind="evaluation_policy", limit=5, offset=0)
            sys_items = (sys_res or {}).get("items") if isinstance(sys_res, dict) else None
            if isinstance(sys_items, list) and sys_items:
                sys_items2 = sorted(sys_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                payload = (sys_items2[0] or {}).get("payload") if isinstance(sys_items2[0], dict) else None
                if isinstance(payload, dict):
                    sys_obj = payload
        except Exception:
            sys_obj = DEFAULT_POLICY

        # If project_id not provided, try to derive from run_start payload context (best-effort)
        if not project_id:
            try:
                start_ev = await store.get_run_start_event(run_id=rid)
                payload0 = (start_ev or {}).get("payload") if isinstance(start_ev, dict) else None
                reqp = (payload0 or {}).get("request_payload") if isinstance(payload0, dict) else None
                ctx0 = (reqp or {}).get("context") if isinstance(reqp, dict) else None
                if isinstance(ctx0, dict) and ctx0.get("project_id"):
                    project_id = str(ctx0.get("project_id")).strip() or None
            except Exception:
                project_id = None

        # project/<project_id> override (partial)
        proj_obj = None
        if project_id:
            try:
                proj_res = await store.list_learning_artifacts(target_type="project", target_id=str(project_id), kind="evaluation_policy", limit=5, offset=0)
                proj_items = (proj_res or {}).get("items") if isinstance(proj_res, dict) else None
                if isinstance(proj_items, list) and proj_items:
                    proj_items2 = sorted(proj_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                    payload = (proj_items2[0] or {}).get("payload") if isinstance(proj_items2[0], dict) else None
                    if isinstance(payload, dict):
                        proj_obj = payload
            except Exception:
                proj_obj = None

        pol_obj = merge_policy(sys_obj, proj_obj or {})
        if isinstance(policy_override, dict):
            pol_obj = merge_policy(pol_obj, policy_override)

        pol = EvaluationPolicy.from_dict(pol_obj).to_dict()
        extra.setdefault("evaluation_policy", pol)
        if project_id:
            extra.setdefault("project_id", project_id)
        if not thresholds0 and isinstance(pol.get("thresholds"), dict):
            thresholds0 = dict(pol.get("thresholds") or {})
        # Resolve tag templates into request defaults (unless caller explicitly set them)
        try:
            templates = pol.get("tag_templates") if isinstance(pol.get("tag_templates"), dict) else {}
            tname = tag_template or str(pol.get("default_tag_template") or "").strip() or None
            if tname and isinstance(templates.get(tname), dict):
                tcfg = templates.get(tname) or {}
                if expected_tags is None and isinstance(tcfg.get("expected_tags"), list):
                    expected_tags = tcfg.get("expected_tags")
                if tag_expectations is None and isinstance(tcfg.get("tag_expectations"), dict):
                    tag_expectations = tcfg.get("tag_expectations")
                extra.setdefault("tag_template", tname)
        except Exception:
            pass
    except Exception:
        pass

    # Build an LLM adapter (prefer persisted adapters, fallback to env).
    provider = str(os.getenv("AIPLAT_AUTO_EVAL_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "mock").strip().lower()
    model = str(os.getenv("AIPLAT_AUTO_EVAL_LLM_MODEL") or os.getenv("LLM_MODEL") or "mock").strip()
    api_key = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") if provider == "openai" else None
    try:
        from core.adapters.llm.base import create_adapter as _mk

        llm = _mk(provider=provider, api_key=api_key, model=model, base_url=base_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"auto_eval_llm_not_available:{e}")

    from core.harness.evaluation.auto import build_auto_eval_prompt, parse_json_report, try_parse_json
    from core.harness.evaluation.workbench import EvaluatorThresholds, apply_threshold_gate, persist_evaluation
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    browser_evidence: Optional[Dict[str, Any]] = None
    evidence_capture_attempts: int = 0
    evidence_capture_error: Optional[str] = None
    if url:
        # Optional: collect browser evidence via MCP integrated_browser tools.
        # This is best-effort and can be disabled by not enabling the MCP server.
        try:
            from core.mcp.runtime_sync import sync_mcp_runtime

            await sync_mcp_runtime(mcp_manager=_mcp_mgr(rt), workspace_mcp_manager=_workspace_mcp_mgr(rt))
        except Exception:
            pass
        pol0 = extra.get("evaluation_policy") if isinstance(extra.get("evaluation_policy"), dict) else {}
        cap = pol0.get("evidence_capture") if isinstance(pol0.get("evidence_capture"), dict) else {}
        try:
            max_retries = int(cap.get("max_retries", 1))
        except Exception:
            max_retries = 1
        max_retries = max(0, min(3, max_retries))  # safety cap
        attempts = 1 + max_retries

        async def _collect_browser_evidence_once() -> Dict[str, Any]:
            from core.apps.tools.base import get_tool_registry
            from core.harness.syscalls.tool import sys_tool_call

            reg = get_tool_registry()
            actor2 = actor_from_http(http_request, body or {})
            user_id = str(actor2.get("actor_id") or "admin")
            session_id = str(actor2.get("session_id") or "auto_eval")
            trace_ctx = {"trace_id": run.get("trace_id"), "run_id": rid, "tenant_id": actor2.get("tenant_id")}

            def _get(name: str):
                t = reg.get(name) if hasattr(reg, "get") else None
                if t is None:
                    try:
                        t = reg.get_tool(name)
                    except Exception:
                        t = None
                return t

            async def _call(tool_full_name: str, args: Dict[str, Any]) -> Any:
                tool_obj = _get(tool_full_name)
                if tool_obj is None:
                    raise RuntimeError(f"missing_tool:{tool_full_name} (请在 MCP库 启用 integrated_browser，并确保该 tool 在 allowed_tools 中)")
                res0 = await sys_tool_call(
                    tool_obj,
                    args,
                    user_id=user_id,
                    session_id=session_id,
                    trace_context=trace_ctx,
                )
                if getattr(res0, "error", None) == "approval_required":
                    meta0 = getattr(res0, "metadata", {}) or {}
                    raise HTTPException(status_code=409, detail={"code": "approval_required", **meta0})
                if getattr(res0, "error", None) in {"policy_denied", "toolset_denied"}:
                    meta0 = getattr(res0, "metadata", {}) or {}
                    raise HTTPException(status_code=403, detail={"code": getattr(res0, "error", None), **meta0})
                if not bool(getattr(res0, "success", True)):
                    raise RuntimeError(getattr(res0, "error", None) or "browser_tool_failed")
                return getattr(res0, "output", None)

            # Default flow: navigate -> wait -> snapshot -> screenshot -> console/network
            be: Dict[str, Any] = {
                "url": url,
                "steps": [],
                "coverage": {"executed_tags": [], "expected_tags": expected_tags or []},
                "by_tag": {},
            }
            _tag_started_at: Dict[str, float] = {}
            _active_tag: Optional[str] = None

            async def _capture_tag(tag: str) -> None:
                by_tag = be.get("by_tag")
                if not isinstance(by_tag, dict):
                    by_tag = {}
                    be["by_tag"] = by_tag
                t0 = str(tag or "").strip()
                if not t0:
                    return
                started = _tag_started_at.get(t0)
                dur_ms = (time.time() - started) * 1000.0 if started else None
                try:
                    snap0 = await _call("mcp.integrated_browser.browser_snapshot", {})
                except Exception:
                    snap0 = None
                try:
                    con0 = await _call("mcp.integrated_browser.browser_console_messages", {})
                except Exception:
                    con0 = None
                try:
                    net0 = await _call("mcp.integrated_browser.browser_network_requests", {})
                except Exception:
                    net0 = None
                try:
                    shot0 = await _call("mcp.integrated_browser.browser_take_screenshot", {})
                except Exception:
                    shot0 = None
                by_tag[t0] = {
                    "snapshot": try_parse_json(snap0),
                    "console_messages": try_parse_json(con0),
                    "network_requests": try_parse_json(net0),
                    "screenshot": try_parse_json(shot0),
                    "duration_ms": dur_ms,
                }

            await _call("mcp.integrated_browser.browser_navigate", {"url": url})
            be["steps"].append({"tool": "browser_navigate", "ok": True, "tag": "navigate"})
            be["coverage"]["executed_tags"].append("navigate")
            try:
                out0 = await _call("mcp.integrated_browser.browser_wait_for", {"timeoutMs": 1500})
                be["steps"].append({"tool": "browser_wait_for", "output": try_parse_json(out0), "tag": "wait_for"})
                be["coverage"]["executed_tags"].append("wait_for")
            except Exception:
                pass
            snap = await _call("mcp.integrated_browser.browser_snapshot", {})
            be["snapshot"] = try_parse_json(snap)
            be["coverage"]["executed_tags"].append("snapshot")
            try:
                shot = await _call("mcp.integrated_browser.browser_take_screenshot", {})
                be["screenshot"] = try_parse_json(shot)
                be["coverage"]["executed_tags"].append("screenshot")
            except Exception:
                pass
            try:
                con = await _call("mcp.integrated_browser.browser_console_messages", {})
                be["console_messages"] = try_parse_json(con)
                be["coverage"]["executed_tags"].append("console")
            except Exception:
                pass
            try:
                net = await _call("mcp.integrated_browser.browser_network_requests", {})
                be["network_requests"] = try_parse_json(net)
                be["coverage"]["executed_tags"].append("network")
            except Exception:
                pass

            # Optional user-provided step list (best-effort). Each step:
            # { "tool": "browser_click|browser_type|browser_scroll|browser_wait_for", "args": {...}, "tag": "login|create|..." }
            if steps:
                for st in steps[:20]:
                    if not isinstance(st, dict):
                        continue
                    tname = str(st.get("tool") or "").strip()
                    args = st.get("args") if isinstance(st.get("args"), dict) else {}
                    tag = str(st.get("tag") or "").strip() or None
                    if tname not in {"browser_click", "browser_type", "browser_scroll", "browser_wait_for"}:
                        continue
                    if tag and tag != _active_tag:
                        if _active_tag:
                            try:
                                await _capture_tag(_active_tag)
                            except Exception:
                                pass
                        _active_tag = tag
                        _tag_started_at.setdefault(tag, time.time())
                    out = await _call(f"mcp.integrated_browser.{tname}", args)
                    be["steps"].append({"tool": tname, "args": args, "output": try_parse_json(out), "tag": tag})
                    if tag:
                        be["coverage"]["executed_tags"].append(tag)
                if _active_tag:
                    try:
                        await _capture_tag(_active_tag)
                    except Exception:
                        pass
            return be

        for i in range(attempts):
            evidence_capture_attempts = i + 1
            try:
                browser_evidence = await _collect_browser_evidence_once()
                evidence_capture_error = None
                break
            except HTTPException:
                raise
            except Exception as e:
                evidence_capture_error = str(e)
                browser_evidence = None
                if i < attempts - 1:
                    continue
                # Do not fail auto eval hard; attach the error so evaluator can fail with evidence.
                browser_evidence = {"url": url, "error": evidence_capture_error, "attempts": evidence_capture_attempts}

        # expose capture stats for prompt/debug
        extra.setdefault("evidence_capture", {"attempts": evidence_capture_attempts, "error": evidence_capture_error})

    # Freeze evidence sampling contract (P0-3):
    # - executed_tags should be stable (dedup + keep order)
    # - compute missing_expected_tags for downstream gates/UI
    try:
        if isinstance(browser_evidence, dict):
            from core.harness.evaluation.coverage_gate import evaluate_coverage, unique_preserve_order

            cov = browser_evidence.get("coverage")
            if not isinstance(cov, dict):
                cov = {}
                browser_evidence["coverage"] = cov
            ex_tags = cov.get("executed_tags") if isinstance(cov.get("executed_tags"), list) else []
            cov["executed_tags"] = unique_preserve_order([str(x) for x in ex_tags])
            exp_tags = cov.get("expected_tags") if isinstance(cov.get("expected_tags"), list) else (expected_tags or [])
            cov["expected_tags"] = unique_preserve_order([str(x) for x in (exp_tags or [])])
            ok_cov, missing = evaluate_coverage(cov.get("expected_tags"), cov.get("executed_tags"))
            cov["missing_expected_tags"] = missing
            cov["ok"] = bool(ok_cov)
    except Exception:
        pass

    evidence_pack_id: Optional[str] = None
    evidence_diff_id: Optional[str] = None
    evidence_diff: Optional[Dict[str, Any]] = None
    # Persist evidence pack (best-effort). This makes evidence queryable and reusable for regression.
    try:
        if browser_evidence is not None:
            mgr = LearningManager(execution_store=store)
            art = await mgr.create_artifact(
                kind=LearningArtifactKind.EVIDENCE_PACK,
                target_type="run",
                target_id=rid,
                version=f"evidence_pack:{int(time.time())}",
                status="draft",
                payload=browser_evidence,
                metadata={
                    "source": "auto_eval",
                    "url": url,
                    "project_id": project_id,
                    "evidence_capture_attempts": evidence_capture_attempts,
                    "evidence_capture_error": evidence_capture_error,
                },
                trace_id=run.get("trace_id"),
                run_id=rid,
            )
            evidence_pack_id = getattr(art, "artifact_id", None)
            extra.setdefault("evidence_pack_id", evidence_pack_id)
            if isinstance(browser_evidence, dict) and evidence_pack_id:
                browser_evidence["evidence_pack_id"] = evidence_pack_id
    except Exception:
        pass

    # Auto evidence diff baseline selection (best-effort)
    # 1) request.base_evidence_pack_id
    # 2) latest PASS evaluation_report under same project_id (via metadata search) -> its evidence_pack_id
    # 3) previous evidence_pack under same run
    try:
        if evidence_pack_id:
            base_artifact_id = None
            base_payload = None

            # (1) explicit override
            if base_evidence_pack_id_req:
                try:
                    base_it = await store.get_learning_artifact(base_evidence_pack_id_req)
                    if isinstance(base_it, dict) and isinstance(base_it.get("payload"), dict):
                        base_artifact_id = str(base_it.get("artifact_id"))
                        base_payload = dict(base_it.get("payload") or {})
                except Exception:
                    base_payload = None

            # (2) project baseline from latest PASS evaluation_report (best-effort)
            if not base_payload and project_id:
                try:
                    marker = f"\"project_id\": \"{project_id}\""
                    rep_res = await store.list_learning_artifacts(
                        kind="evaluation_report",
                        metadata_contains=marker,
                        limit=50,
                        offset=0,
                    )
                    rep_items = (rep_res or {}).get("items") if isinstance(rep_res, dict) else None
                    if isinstance(rep_items, list):
                        rep2 = sorted(rep_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                        for it in rep2:
                            p = (it or {}).get("payload") if isinstance(it, dict) else None
                            if not isinstance(p, dict):
                                continue
                            if not bool(p.get("pass")):
                                continue
                            eid = p.get("evidence_pack_id")
                            if not eid or str(eid) == str(evidence_pack_id):
                                continue
                            base_it = await store.get_learning_artifact(str(eid))
                            if isinstance(base_it, dict) and isinstance(base_it.get("payload"), dict):
                                base_artifact_id = str(base_it.get("artifact_id"))
                                base_payload = dict(base_it.get("payload") or {})
                                break
                except Exception:
                    base_payload = None

            # (3) fallback to previous evidence_pack under same run
            if not base_payload:
                prev_res = await store.list_learning_artifacts(
                    target_type="run",
                    target_id=rid,
                    kind="evidence_pack",
                    limit=5,
                    offset=0,
                )
                prev_items = (prev_res or {}).get("items") if isinstance(prev_res, dict) else None
                if isinstance(prev_items, list) and len(prev_items) >= 2:
                    # newest item is our current evidence pack; take the next one as base
                    prev2 = sorted(prev_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                    base_it = prev2[1]
                    bp = (base_it or {}).get("payload") if isinstance(base_it, dict) else None
                    if isinstance(bp, dict):
                        base_artifact_id = str((base_it or {}).get("artifact_id"))
                        base_payload = dict(bp)

            if isinstance(base_payload, dict) and isinstance(browser_evidence, dict) and base_artifact_id:
                base_payload.setdefault("evidence_pack_id", base_artifact_id)
                browser_evidence.setdefault("evidence_pack_id", evidence_pack_id)
                from core.harness.evaluation.evidence_diff import compute_evidence_diff

                evidence_diff = compute_evidence_diff(base_payload, browser_evidence)
                mgr = LearningManager(execution_store=store)
                art2 = await mgr.create_artifact(
                    kind=LearningArtifactKind.EVIDENCE_DIFF,
                    target_type="run",
                    target_id=rid,
                    version=f"evidence_diff:{int(time.time())}",
                    status="draft",
                    payload=evidence_diff,
                    metadata={
                        "source": "auto_eval",
                        "project_id": project_id,
                        "base_evidence_pack_id": str(base_artifact_id),
                        "new_evidence_pack_id": str(evidence_pack_id),
                    },
                    trace_id=run.get("trace_id"),
                    run_id=rid,
                )
                evidence_diff_id = getattr(art2, "artifact_id", None)
                extra.setdefault("evidence_diff_id", evidence_diff_id)
                extra.setdefault("evidence_diff_summary", (evidence_diff or {}).get("summary"))
    except Exception:
        pass

    msgs = build_auto_eval_prompt(run=run, events=events, extra=extra, browser_evidence=browser_evidence)
    try:
        resp = await llm.generate(msgs)
        text = getattr(resp, "content", "") or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"auto_eval_failed:{e}")

    report, why = parse_json_report(text)
    if report is None:
        report = {
            "pass": False,
            "score": {"functionality": 0, "product_depth": 0, "design_ux": 0, "code_architecture": 0, "overall": 0},
            "issues": [
                {
                    "severity": "P0",
                    "title": "自动评估输出无法解析为 JSON",
                    "repro_steps": [],
                    "expected": "LLM 输出符合约定的 JSON 报告格式",
                    "actual": f"{why}: {text[:800]}",
                    "suggested_fix": "检查 auto_eval 模型配置，或改用手动提交 report。",
                }
            ],
            "positive_notes": [],
            "next_actions_for_generator": ["配置可用的 LLM_PROVIDER/LLM_MODEL 或 AIPLAT_AUTO_EVAL_LLM_PROVIDER/MODEL 后重试"],
        }
    # Attach evidence reference for downstream run_state/todo generation.
    try:
        if isinstance(report, dict) and evidence_pack_id:
            report.setdefault("evidence_pack_id", evidence_pack_id)
        if isinstance(report, dict) and evidence_diff_id:
            report.setdefault("evidence_diff_id", evidence_diff_id)
            if evidence_diff:
                report.setdefault("evidence_diff_summary", evidence_diff.get("summary"))
    except Exception:
        pass

    thresholds = EvaluatorThresholds.from_dict(thresholds0)
    gated_report = apply_threshold_gate(report, thresholds)

    # Coverage gate (hard, P0-3): expected tags must be executed when url evidence is enabled.
    try:
        if isinstance(browser_evidence, dict):
            from core.harness.evaluation.coverage_gate import evaluate_coverage

            exp = None
            cov = browser_evidence.get("coverage")
            if isinstance(cov, dict) and isinstance(cov.get("expected_tags"), list):
                exp = cov.get("expected_tags")
            if not exp:
                polx = extra.get("evaluation_policy") if isinstance(extra.get("evaluation_policy"), dict) else {}
                gate0 = polx.get("regression_gate") if isinstance(polx.get("regression_gate"), dict) else {}
                exp = gate0.get("required_tags") if isinstance(gate0.get("required_tags"), list) else None
            executed = None
            if isinstance(cov, dict) and isinstance(cov.get("executed_tags"), list):
                executed = cov.get("executed_tags")
            ok_cov, missing = evaluate_coverage(exp, executed)
            gated_report.setdefault("coverage", {})
            gated_report["coverage"]["expected_tags"] = exp or []
            gated_report["coverage"]["executed_tags"] = executed or []
            gated_report["coverage"]["missing_expected_tags"] = missing
            if (exp or []) and (not ok_cov):
                gated_report["pass"] = False
                gated_report.setdefault("issues", [])
                if isinstance(gated_report.get("issues"), list):
                    gated_report["issues"].insert(
                        0,
                        {
                            "severity": "P0",
                            "title": "关键路径覆盖不足（Coverage Gate）",
                            "expected": {"expected_tags": exp, "note": "执行 steps 时请为关键步骤标注 tag"},
                            "actual": {"executed_tags": executed, "missing_expected_tags": missing},
                            "repro_steps": [],
                            "evidence": {"evidence_pack_id": evidence_pack_id},
                            "suggested_fix": "为浏览器步骤 steps[] 补齐 tag（或调整 expected_tags / required_tags），确保关键路径被执行后再评估。",
                        },
                    )
    except Exception:
        pass

    # Tag assertions (hard gate): based on evidence_pack.by_tag + tag_expectations
    try:
        if isinstance(browser_evidence, dict) and isinstance(tag_expectations, dict) and tag_expectations:
            from core.harness.evaluation.tag_assertions import evaluate_tag_assertions_with_stats

            ok, failures, stats = evaluate_tag_assertions_with_stats(browser_evidence, tag_expectations)
            gated_report.setdefault("assertions", {})
            gated_report["assertions"]["tag_expectations"] = tag_expectations
            gated_report["assertions"]["tag_failures"] = failures
            gated_report["assertions"]["tag_stats"] = stats
            if not ok:
                gated_report["pass"] = False
                gated_report.setdefault("issues", [])
                if isinstance(gated_report.get("issues"), list):
                    gated_report["issues"].insert(
                        0,
                        {
                            "severity": "P0",
                            "title": "关键路径断言未通过（Tag Assertions）",
                            "expected": tag_expectations,
                            "actual": {"failures": failures[:20]},
                            "repro_steps": [],
                            "evidence": {"evidence_pack_id": evidence_pack_id, "evidence_diff_id": evidence_diff_id},
                            "suggested_fix": "补齐关键路径交互与可见性/接口稳定性后重新评估。",
                        },
                    )
    except Exception:
        pass

    # Regression gate based on evidence_diff metrics (best-effort)
    try:
        pol = extra.get("evaluation_policy") if isinstance(extra.get("evaluation_policy"), dict) else None
        gate = (pol or {}).get("regression_gate") if isinstance((pol or {}).get("regression_gate"), dict) else None
        if gate and evidence_diff:
            from core.harness.evaluation.evidence_diff import evaluate_regression

            executed_tags = None
            try:
                if isinstance(browser_evidence, dict):
                    cov = browser_evidence.get("coverage")
                    if isinstance(cov, dict) and isinstance(cov.get("executed_tags"), list):
                        executed_tags = cov.get("executed_tags")
            except Exception:
                executed_tags = None
            is_reg, reasons = evaluate_regression(evidence_diff, gate, executed_tags=executed_tags)
            gated_report.setdefault("regression", {})
            gated_report["regression"] = {
                "is_regression": bool(is_reg),
                "reasons": reasons,
                "gate": gate,
                "evidence_diff_id": evidence_diff_id,
            }
            if is_reg:
                gated_report["pass"] = False
                gated_report.setdefault("issues", [])
                if isinstance(gated_report.get("issues"), list):
                    gated_report["issues"].insert(
                        0,
                        {
                            "severity": "P0",
                            "title": "回归对比未通过（Evidence Diff Regression Gate）",
                            "expected": gate,
                            "actual": (evidence_diff.get("metrics") if isinstance(evidence_diff, dict) else {}),
                            "repro_steps": [],
                            "evidence": {"evidence_diff_id": evidence_diff_id, "summary": evidence_diff.get("summary") if isinstance(evidence_diff, dict) else ""},
                            "suggested_fix": "检查新增 console error / network 5xx 等回归信号，并修复后重新评估。",
                        },
                    )
    except Exception:
        pass
    actor = actor_from_http(http_request, request or {})
    saved = await persist_evaluation(
        execution_store=store,
        run_id=rid,
        trace_id=run.get("trace_id"),
        evaluator=evaluator,
        report=gated_report,
        thresholds=thresholds,
        actor=actor,
    )
    # Update run_state (best-effort) from evaluator report
    try:
        from core.harness.restatement.run_state import merge_from_evaluation, normalize_run_state

        mgr = LearningManager(execution_store=store)
        latest = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="run_state", limit=10, offset=0)
        items = latest.get("items") if isinstance(latest, dict) else None
        cur = {}
        if isinstance(items, list) and items:
            items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
            cur = (items2[0] or {}).get("payload") if isinstance(items2[0], dict) else {}
        cur2 = normalize_run_state(cur, run_id=rid)
        if not str(cur2.get("task") or "").strip():
            cur2["task"] = str(run.get("task") or "")
        merged = merge_from_evaluation(cur2, evaluation_report=gated_report, source="auto_eval")
        await mgr.create_artifact(
            kind=LearningArtifactKind.RUN_STATE,
            target_type="run",
            target_id=rid,
            version=f"run_state:{int(time.time())}",
            status="draft",
            payload=merged,
            metadata={"source": "auto_eval", "locked": bool(merged.get("locked"))},
            trace_id=run.get("trace_id"),
            run_id=rid,
        )
    except Exception:
        pass
    if enforce_gate and not bool(gated_report.get("pass")):
        raise HTTPException(status_code=409, detail={"code": "evaluation_failed", "artifact_id": saved.get("artifact_id"), "report": gated_report})
    return {"status": "ok", "artifact_id": saved.get("artifact_id"), "report": gated_report, "raw": text[:2000]}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, http_request: Request, body: Optional[Dict[str, Any]] = None, rt: RuntimeDep = None):
    """
    Best-effort stop/cancel for platform runs.
    - If run is queued (session_queue), mark it cancelled so it won't be dequeued.
    - Always write a cancel_requested marker to run_events.
    - If run has no run_end yet, append run_end(status=cancelled) so UI becomes stable.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    actor = actor_from_http(http_request, None)
    reason = str((body or {}).get("reason") or "user_requested") if isinstance(body, dict) else "user_requested"
    cancelled_queued = False
    try:
        cancelled_queued = await store.cancel_queued_run(run_id=rid)
    except Exception:
        cancelled_queued = False
    try:
        await store.append_run_event(
            run_id=rid,
            event_type="cancel_requested",
            trace_id=run.get("trace_id"),
            tenant_id=actor.get("tenant_id"),
            payload={"reason": reason, "actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
        )
    except Exception:
        pass
    try:
        if not await store.has_run_end(run_id=rid):
            await store.append_run_event(
                run_id=rid,
                event_type="run_end",
                trace_id=run.get("trace_id"),
                tenant_id=actor.get("tenant_id"),
                payload={"status": "cancelled", "reason": reason},
            )
    except Exception:
        pass
    return {"status": "cancel_requested", "run_id": rid, "cancelled_queued": bool(cancelled_queued)}


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str, http_request: Request, rt: RuntimeDep = None):
    """
    Best-effort retry for platform runs.
    This replays the run_start.request_payload captured in run_events (redacted),
    and re-executes via Harness with a new run_id.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    start = await store.get_run_start_event(run_id=rid)
    if not start:
        raise HTTPException(status_code=404, detail="run_not_found")
    payload = start.get("payload") if isinstance(start, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    kind = str(payload.get("kind") or "").strip()
    req_payload = payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {}
    user_id = str(payload.get("user_id") or "system")
    session_id = str(payload.get("session_id") or "default")
    target_id = None
    if kind == "agent":
        target_id = payload.get("agent_id")
    elif kind == "skill":
        target_id = payload.get("skill_id")
    elif kind == "tool":
        target_id = payload.get("tool_name")
    elif kind == "graph":
        target_id = payload.get("graph_name") or payload.get("target_id")
    elif kind == "smoke_e2e":
        target_id = "smoke_e2e"
    if not kind or not target_id:
        raise HTTPException(status_code=409, detail="retry_not_supported")

    from core.utils.ids import new_prefixed_id

    new_id = new_prefixed_id("run")
    req = ExecutionRequest(
        kind=kind,  # type: ignore[arg-type]
        target_id=str(target_id),
        payload=req_payload if isinstance(req_payload, dict) else {},
        user_id=user_id,
        session_id=session_id,
        run_id=new_id,
    )
    result = await get_harness().execute(req)
    resp = wrap_execution_result_as_run_summary(result)
    resp["previous_run_id"] = rid
    resp["new_run_id"] = new_id
    return resp


@router.post("/runs/{run_id}/undo")
async def undo_run(run_id: str, http_request: Request, body: Optional[Dict[str, Any]] = None, rt: RuntimeDep = None):
    """
    Minimal "undo" for runs: if the run is still queued, cancel it.
    (For completed runs, undo is not generally defined; use domain-specific rollback endpoints.)
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    q = None
    try:
        q = await store.get_session_queue_item(run_id=rid)
    except Exception:
        q = None
    if q and str(q.get("status") or "") == "queued":
        out = await cancel_run(run_id=rid, http_request=http_request, body={"reason": str((body or {}).get("reason") or "undo_queued")}, rt=rt)
        out["status"] = "undone"
        return out
    raise HTTPException(status_code=409, detail="undo_not_supported")


@router.post("/runs/{run_id}/wait")
async def wait_run(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Long-poll run events until terminal state or timeout.
    Body:
      { "timeout_ms": 30000, "after_seq": 0, "auto_resume": false }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    timeout_ms = int((request or {}).get("timeout_ms") or 30000)
    after_seq = int((request or {}).get("after_seq") or 0)
    auto_resume_requested = (request or {}).get("auto_resume", None)
    # P4: auto-resume is opt-in and additionally gated by server config + tenant policy + RBAC.
    enabled_env = os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ENABLED", "false").lower() in {"1", "true", "yes", "y"}
    default_auto_resume_env = os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_DEFAULT", "false").lower() in {"1", "true", "yes", "y"}
    allowlist_env = os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ALLOWLIST", "*").strip()
    auto_resume = bool(auto_resume_requested) if auto_resume_requested is not None else bool(default_auto_resume_env)
    enabled = bool(enabled_env)
    allowlist_raw = allowlist_env
    deadline = time.time() + max(1, timeout_ms) / 1000.0

    async def _resolve_approval_request_id(*, rid: str, run0: Dict[str, Any], evs: list) -> Optional[str]:
        # 1) run_events (tool path and new skill path)
        try:
            for e in reversed(evs or []):
                if e.get("type") == "approval_requested":
                    pid = (e.get("payload") or {}).get("approval_request_id")
                    if isinstance(pid, str) and pid:
                        return pid
        except Exception:
            pass
        # 2) run.error.extra.approval_request_id (skill/tool normalization path)
        try:
            err = run0.get("error") if isinstance(run0.get("error"), dict) else None
            extra = (err or {}).get("extra") if isinstance((err or {}).get("extra"), dict) else None
            pid = (extra or {}).get("approval_request_id")
            if isinstance(pid, str) and pid:
                return pid
        except Exception:
            pass
        # 3) approval_requests table lookup by run_id (best-effort)
        try:
            res = await store.list_approval_requests(run_id=str(rid), status="pending", limit=5, offset=0)
            for it in (res.get("items") or []):
                pid = it.get("request_id")
                if isinstance(pid, str) and pid:
                    return pid
        except Exception:
            pass
        return None

    def _resolve_checkpoint(*, evs: list) -> Optional[Dict[str, Any]]:
        try:
            for e in reversed(evs or []):
                if e.get("type") == "checkpoint_requested":
                    payload = e.get("payload") if isinstance(e.get("payload"), dict) else None
                    if payload and payload.get("checkpoint_id"):
                        return payload
        except Exception:
            return None
        return None

    def _resolve_join_ready(*, evs: list) -> Optional[Dict[str, Any]]:
        try:
            for e in reversed(evs or []):
                if e.get("type") == "join_ready":
                    payload = e.get("payload") if isinstance(e.get("payload"), dict) else None
                    if payload and payload.get("join_id"):
                        return payload
        except Exception:
            return None
        return None

    async def _maybe_auto_resume(*, rid: str, approval_id: str) -> bool:
        """
        If approval is approved, replay it automatically on the same run_id.
        Returns True if a replay was triggered.
        """
        if not approval_id:
            return False
        # Allowlist gate (defense-in-depth). Only applies when auto-resume feature is enabled.
        allow_patterns = [p.strip() for p in str(allowlist_raw or "*").split(",") if p.strip()] or ["*"]
        runtime = rt or get_kernel_runtime()
        if runtime is None:
            return False
        approval_mgr = getattr(runtime, "approval_manager", None)
        if approval_mgr is None:
            return False
        try:
            req0 = await approval_mgr.get_request_async(str(approval_id)) if hasattr(approval_mgr, "get_request_async") else approval_mgr.get_request(str(approval_id))
        except Exception:
            req0 = None
        if not req0:
            return False
        try:
            status = getattr(req0, "status", None)
            from core.harness.infrastructure.approval.types import RequestStatus

            if status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
                return False
        except Exception:
            return False
        try:
            rec = await store.get_approval_request(str(approval_id))
        except Exception:
            rec = None
        if not isinstance(rec, dict):
            return False
        op = str(rec.get("operation") or "")
        try:
            import fnmatch

            if allow_patterns and not any(fnmatch.fnmatch(op, pat) for pat in allow_patterns):
                return False
        except Exception:
            pass
        meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        opctx = meta.get("operation_context") if isinstance(meta.get("operation_context"), dict) else {}
        # Prepare replay payload similar to approvals hub.
        ctx = {
            "tenant_id": meta.get("tenant_id") or rec.get("tenant_id"),
            "actor_id": meta.get("actor_id") or rec.get("actor_id") or rec.get("user_id"),
            "actor_role": meta.get("actor_role") or rec.get("actor_role"),
            "session_id": meta.get("session_id") or rec.get("session_id"),
            "entrypoint": "runs_wait",
            "source": "runs_wait",
        }
        # Fallback: bind tenant_id from run summary when missing, so replay can load tenant policy.
        try:
            if not ctx.get("tenant_id") and store:
                run0 = await store.get_run_summary(run_id=str(rid))
                if isinstance(run0, dict) and run0.get("tenant_id"):
                    ctx["tenant_id"] = str(run0.get("tenant_id"))
        except Exception:
            pass
        h = get_harness()
        if op.startswith("tool:"):
            # If this run_id belongs to a skill execution, prefer resuming the skill itself so the run status/output
            # moves to completed (otherwise a tool execution with same run_id would not override get_run_summary()).
            try:
                run0 = await store.get_run_summary(run_id=str(rid)) if store else None
            except Exception:
                run0 = None
            if isinstance(run0, dict) and str(run0.get("kind") or "") == "skill":
                start = None
                try:
                    start = await store.get_run_start_event(run_id=str(rid)) if store else None
                except Exception:
                    start = None
                payload0 = (start or {}).get("payload") if isinstance(start, dict) else {}
                reqp = (payload0 or {}).get("request_payload") if isinstance(payload0, dict) else {}
                inp = (reqp or {}).get("input") if isinstance(reqp, dict) else {}
                ctx_in = (reqp or {}).get("context") if isinstance(reqp, dict) else {}
                inp = dict(inp) if isinstance(inp, dict) else {}
                inp["_approval_request_id"] = str(approval_id)
                skill_id0 = (payload0 or {}).get("skill_id") if isinstance(payload0, dict) else None
                if not skill_id0:
                    skill_id0 = (run0 or {}).get("target_id")
                exec_req = ExecutionRequest(
                    kind="skill",
                    target_id=str(skill_id0),
                    payload={"input": inp, "context": dict(ctx_in) if isinstance(ctx_in, dict) else ctx},
                    user_id=str(ctx.get("actor_id") or "system"),
                    session_id=str(ctx.get("session_id") or "default"),
                    run_id=str(rid),
                )
                await h.execute(exec_req)
            else:
                tool_name = op.split(":", 1)[1]
                tool_args = opctx.get("args") if isinstance(opctx, dict) else None
                tool_args = dict(tool_args) if isinstance(tool_args, dict) else {}
                tool_args["_approval_request_id"] = str(approval_id)
                exec_req = ExecutionRequest(
                    kind="tool",
                    target_id=str(tool_name),
                    payload={"input": tool_args, "context": ctx},
                    user_id=str(ctx.get("actor_id") or "system"),
                    session_id=str(ctx.get("session_id") or "default"),
                    run_id=str(rid),
                )
                await h.execute(exec_req)
            try:
                await store.append_run_event(
                    run_id=str(rid),
                    event_type="approval_replayed",
                    trace_id=None,
                    tenant_id=str(ctx.get("tenant_id")) if ctx.get("tenant_id") else None,
                    payload={"approval_request_id": str(approval_id), "operation": op, "source": "runs_wait"},
                )
            except Exception:
                pass
            return True
        if op.startswith("skill:"):
            skill_id = op.split(":", 1)[1]
            skill_args = opctx.get("args") if isinstance(opctx, dict) else None
            skill_args = dict(skill_args) if isinstance(skill_args, dict) else {}
            skill_args["_approval_request_id"] = str(approval_id)
            exec_req = ExecutionRequest(
                kind="skill",
                target_id=str(skill_id),
                payload={"input": skill_args, "context": ctx},
                user_id=str(ctx.get("actor_id") or "system"),
                session_id=str(ctx.get("session_id") or "default"),
                run_id=str(rid),
            )
            await h.execute(exec_req)
            try:
                await store.append_run_event(
                    run_id=str(rid),
                    event_type="approval_replayed",
                    trace_id=None,
                    tenant_id=str(ctx.get("tenant_id")) if ctx.get("tenant_id") else None,
                    payload={"approval_request_id": str(approval_id), "operation": op, "source": "runs_wait"},
                )
            except Exception:
                pass
            return True
        return False

    # quick check
    run = await store.get_run_summary(run_id=str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    # Tenant policy override (best-effort):
    # policy.run_wait_auto_resume = { enabled: bool, default: bool, allowlist: "skill:*,tool:*" }
    try:
        tenant_id = run.get("tenant_id") or (actor_from_http(http_request, request if isinstance(request, dict) else None).get("tenant_id"))
        if tenant_id:
            pol_rec = await store.get_tenant_policy(tenant_id=str(tenant_id))
            pol = pol_rec.get("policy") if isinstance(pol_rec, dict) else None
            rpol = (pol or {}).get("run_wait_auto_resume") if isinstance(pol, dict) else None
            if isinstance(rpol, dict):
                if isinstance(rpol.get("enabled"), bool):
                    enabled = bool(rpol.get("enabled"))
                if isinstance(rpol.get("default"), bool) and auto_resume_requested is None:
                    auto_resume = bool(rpol.get("default"))
                if isinstance(rpol.get("allowlist"), str) and str(rpol.get("allowlist")).strip():
                    allowlist_raw = str(rpol.get("allowlist")).strip()
    except Exception:
        pass

    if not enabled:
        auto_resume = False

    last_seq = after_seq
    events: list = []
    done = False
    replayed = False

    while time.time() < deadline:
        batch = await store.list_run_events(run_id=str(run_id), after_seq=last_seq, limit=200)
        new_events = batch.get("items") or []
        saw_run_end = False
        if new_events:
            events.extend(new_events)
            last_seq = int(batch.get("last_seq") or last_seq)
            saw_run_end = any(e.get("type") == "run_end" for e in new_events)
            # If caller doesn't want auto resume, return immediately when approval is requested.
            if (not auto_resume) and any(e.get("type") == "approval_requested" for e in new_events):
                done = True
                break
            # Always return when a checkpoint is requested (human-in-the-loop).
            if any(e.get("type") == "checkpoint_requested" for e in new_events):
                done = True
                break
            # Always return when a join barrier is ready.
            if any(e.get("type") == "join_ready" for e in new_events):
                done = True
                break
        # refresh run status (best-effort)
        run = await store.get_run_summary(run_id=str(run_id)) or run
        # done when reaching terminal or waiting_approval (paused)
        legacy = str(run.get("status") or "")
        err_code = run.get("error_code")
        try:
            if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
                err_code = (run.get("error") or {}).get("code")
        except Exception:
            pass
        st2 = normalize_run_status_v2(ok=legacy == "completed", legacy_status=legacy, error_code=err_code)
        if st2 in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value}:
            done = True
            break
        # Some executions emit a run_end even when they are effectively paused (waiting_approval).
        # For auto-resume callers, do not treat that run_end as terminal; keep polling.
        if saw_run_end and (not (auto_resume and st2 == RunStatus.waiting_approval.value)):
            done = True
            break
        # waiting_approval: optionally auto-resume
        if st2 == RunStatus.waiting_approval.value:
            approval_id = await _resolve_approval_request_id(rid=str(run_id), run0=run, evs=events)
            if auto_resume and approval_id and (not replayed):
                # RBAC: only operator/admin can trigger auto-resume (developer/viewer denied).
                try:
                    from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce

                    actor = actor_from_http(http_request, request if isinstance(request, dict) else None)
                    dec = rbac_check_permission(actor_role=actor.get("actor_role"), action="resume", resource_type="run")
                    if not dec.allowed:
                        if rbac_should_enforce():
                            deny = await rbac_guard(
                                http_request=http_request,
                                payload=request if isinstance(request, dict) else None,
                                action="resume",
                                resource_type="run",
                                resource_id=str(run_id),
                                run_id=str(run_id),
                            )
                            if deny:
                                return deny
                        # fail-closed: disable auto resume for this call
                        auto_resume = False
                except Exception:
                    # fail-closed
                    auto_resume = False
                try:
                    replayed = await _maybe_auto_resume(rid=str(run_id), approval_id=str(approval_id))
                except Exception:
                    replayed = False
                # After triggering replay, continue waiting for run_end/terminal within same call.
            if not auto_resume:
                done = True
                break
        await asyncio.sleep(0.5)

    # normalize run to v2 contract
    legacy_status = run.get("status")
    err_code = run.get("error_code")
    try:
        if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
            err_code = (run.get("error") or {}).get("code")
    except Exception:
        pass
    status2 = normalize_run_status_v2(ok=str(legacy_status) == "completed", legacy_status=legacy_status, error_code=err_code)
    ok2 = status2 not in {RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value, RunStatus.waiting_approval.value}
    err_obj = None
    if not ok2:
        err_obj = normalize_run_error(
            code=err_code or (run.get("error") or {}).get("code") if isinstance(run.get("error"), dict) else None,
            message=run.get("error_message") or (run.get("error") or {}).get("message") if isinstance(run.get("error"), dict) else None,
            detail=(run.get("error") or {}).get("detail") if isinstance(run.get("error"), dict) else None,
        )
    run2 = dict(run)
    run2["ok"] = ok2
    run2["legacy_status"] = legacy_status
    run2["status"] = status2
    run2["error"] = None if ok2 else err_obj
    run2["output"] = run.get("output")
    approval_request_id = await _resolve_approval_request_id(rid=str(run_id), run0=run, evs=events)
    if approval_request_id:
        run2["approval_request_id"] = str(approval_request_id)
    checkpoint = _resolve_checkpoint(evs=events)
    join_ready = _resolve_join_ready(evs=events)
    return {
        "run": run2,
        "events": events,
        "after_seq": after_seq,
        "last_seq": last_seq,
        "done": done,
        "approval_request_id": str(approval_request_id) if approval_request_id else None,
        "auto_resumed": bool(replayed),
        "checkpoint": checkpoint,
        "join": join_ready,
    }


@router.get("/runs/{run_id}/evidence")
async def get_run_evidence(run_id: str, limit: int = 50, rt: RuntimeDep = None):
    """
    Lightweight evidence endpoint for reviewers/UI:
    - syscall_events (most recent)
    - key run_events (most recent)
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    syscalls = await store.list_syscall_events(run_id=rid, limit=int(limit), offset=0)
    ev = await store.list_run_events(run_id=rid, after_seq=0, limit=800)
    items = ev.get("items") or []
    key_types = {
        "run_start",
        "run_end",
        "child_run_spawned",
        "child_run_parent",
        "checkpoint_requested",
        "checkpoint_resolved",
        "checkpoint_applied",
        "join_defined",
        "join_ready",
        "node_invalidated",
        "stale",
        "approval_waived",
        "persona_applied",
    }
    run_events = []
    for e in items:
        if e.get("type") in key_types:
            run_events.append({"seq": e.get("seq"), "type": e.get("type"), "created_at": e.get("created_at"), "payload": e.get("payload")})
    run_events = list(reversed(run_events))[: int(limit)]
    return {
        "run_id": rid,
        "syscalls": _summarize_syscalls(syscalls.get("items") if isinstance(syscalls, dict) else []),
        "run_events": run_events,
    }
