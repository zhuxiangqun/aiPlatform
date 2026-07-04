from __future__ import annotations
from core.schemas_common import MessageResponse

# ════════════════════════════════════════════════════════════════════════
# STRUCTURAL DEBT: 3590 lines — split partially executed (audit 1.7).
#   runs_eval.py       — ✅ skeleton created, endpoint migration pending
#   runs_learning.py   — pending
#   runs_deploy.py     — pending
# Target: each file < 1000 lines.
# ════════════════════════════════════════════════════════════════════════


import asyncio
import os
import time
from typing import Any, Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.run_contract import normalize_run_error, normalize_run_status_v2, wrap_execution_result_as_run_summary
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas_eval import AutoEvalRequest, EvidenceDiffRequest
from core.schemas_run import RunStatus
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url
import logging

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


@router.get("/runs/{run_id}", response_model=Dict[str, Any])
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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


@router.get("/runs/{run_id}/events", response_model=Dict[str, Any])
async def list_run_events(run_id: str, after_seq: int = 0, limit: int = 200, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_run_events(run_id=str(run_id), after_seq=int(after_seq or 0), limit=int(limit or 200))


@router.get("/runs/{run_id}/cost", response_model=Dict[str, Any])
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


@router.get("/runs/{run_id}/children", response_model=Dict[str, Any])
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


@router.get("/runs/{run_id}/graph", response_model=Dict[str, Any])
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
@router.post("/runs/{run_id}/children/spawn", response_model=Dict[str, Any])
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
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                if (not routed_risk) and isinstance(pr.get("default_risk_by_kind"), dict):
                    try:
                        drk = pr.get("default_risk_by_kind") if isinstance(pr.get("default_risk_by_kind"), dict) else {}
                        rl0 = drk.get(kind)
                        if isinstance(rl0, str) and rl0.strip():
                            routed_risk = rl0.strip().lower()
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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


@router.post("/runs/{run_id}/joins/define", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/joins/{join_id}/wait", response_model=Dict[str, Any])
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
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
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

@router.post("/runs/{run_id}/nodes/{node_id}/redo", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/checkpoints/request", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/resolve", response_model=Dict[str, Any])
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    try:
        await store.append_run_event(
            run_id=str(new_child_id),
            event_type="child_run_parent",
            trace_id=resp.get("trace_id"),
            tenant_id=tenant_id,
            payload={"parent_run_id": parent_id, "node_id": str(node_id)},
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                    try:
                        await store.append_run_event(
                            run_id=str(dn_child),
                            event_type="stale",
                            trace_id=None,
                            tenant_id=tenant_id,
                            payload={"because_node": str(node_id), "parent_run_id": parent_id, "reason": "upstream_redo"},
                        )
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
    except Exception:
        invalidated = invalidated
    resp["invalidated"] = invalidated
    return resp


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/apply", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/redo", response_model=Dict[str, Any])
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    return resp


@router.post("/runs/{run_id}/cancel", response_model=MessageResponse)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    try:
        if not await store.has_run_end(run_id=rid):
            await store.append_run_event(
                run_id=rid,
                event_type="run_end",
                trace_id=run.get("trace_id"),
                tenant_id=actor.get("tenant_id"),
                payload={"status": "cancelled", "reason": reason},
            )
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return {"status": "cancel_requested", "run_id": rid, "cancelled_queued": bool(cancelled_queued)}


@router.post("/runs/{run_id}/retry", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/undo", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/wait", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        # 2) run.error.extra.approval_request_id (skill/tool normalization path)
        try:
            err = run0.get("error") if isinstance(run0.get("error"), dict) else None
            extra = (err or {}).get("extra") if isinstance((err or {}).get("extra"), dict) else None
            pid = (extra or {}).get("approval_request_id")
            if isinstance(pid, str) and pid:
                return pid
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        # 3) approval_requests table lookup by run_id (best-effort)
        try:
            res = await store.list_approval_requests(run_id=str(rid), status="pending", limit=5, offset=0)
            for it in (res.get("items") or []):
                pid = it.get("request_id")
                if isinstance(pid, str) and pid:
                    return pid
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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


