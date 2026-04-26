from __future__ import annotations

import io
import json
import time
import zipfile
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.api.deps.rbac import actor_from_http
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.governance.verification import apply_autosmoke_result, mark_resource_pending
from core.harness.kernel.runtime import get_kernel_runtime


router = APIRouter()


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _job_scheduler():
    rt = get_kernel_runtime()
    return getattr(rt, "job_scheduler", None) if rt else None


def _workspace_managers():
    rt = get_kernel_runtime()
    return (
        getattr(rt, "workspace_agent_manager", None) if rt else None,
        getattr(rt, "workspace_skill_manager", None) if rt else None,
        getattr(rt, "workspace_mcp_manager", None) if rt else None,
    )


@router.get("/change-control/changes")
async def list_change_controls(limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None):
    """List Change Control items (derived from syscall_events changesets)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    res = await store.list_change_controls(limit=limit, offset=offset, tenant_id=tenant_id)
    items = []
    for it in res.get("items") or []:
        cid = str(it.get("change_id") or it.get("target_id") or "")
        links = {
            "syscalls_ui": ui_url(f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={cid}"),
            "audit_ui": ui_url(f"/diagnostics/audit?change_id={cid}"),
        }
        arid = it.get("approval_request_id")
        if arid:
            links["approvals_ui"] = ui_url("/core/approvals")
            links["audit_request_ui"] = ui_url(f"/diagnostics/audit?request_id={arid}")
        tid = it.get("trace_id")
        rid = it.get("run_id")
        if tid:
            links["traces_ui"] = ui_url(f"/diagnostics/traces?trace_id={tid}")
            links["links_ui"] = ui_url(f"/diagnostics/links?trace_id={tid}")
        if rid:
            links["runs_ui"] = ui_url(f"/diagnostics/runs?run_id={rid}")
        items.append({**it, "change_id": cid, "links": links})
    return {**res, "items": items}


@router.get("/change-control/changes/{change_id}")
async def get_change_control(change_id: str, limit: int = 200, offset: int = 0, tenant_id: Optional[str] = None):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    out = await store.get_change_control(change_id=change_id, limit=limit, offset=offset, tenant_id=tenant_id)
    cid = str(change_id)
    links = {
        "syscalls_ui": ui_url(f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={cid}"),
        "audit_ui": ui_url(f"/diagnostics/audit?change_id={cid}"),
    }
    try:
        latest = out.get("latest") if isinstance(out.get("latest"), dict) else {}
        arid = (latest or {}).get("approval_request_id")
        tid = (latest or {}).get("trace_id")
        rid = (latest or {}).get("run_id")
        if arid:
            links["approvals_ui"] = ui_url("/core/approvals")
            links["audit_request_ui"] = ui_url(f"/diagnostics/audit?request_id={arid}")
        if tid:
            links["traces_ui"] = ui_url(f"/diagnostics/traces?trace_id={tid}")
            links["links_ui"] = ui_url(f"/diagnostics/links?trace_id={tid}")
        if rid:
            links["runs_ui"] = ui_url(f"/diagnostics/runs?run_id={rid}")
    except Exception:
        pass
    out["links"] = links
    return out


@router.post("/change-control/changes/{change_id}/autosmoke")
async def autosmoke_change_control(change_id: str, http_request: Request):
    """
    Trigger autosmoke for targets referenced by a change_id (best-effort).
    - Extract targets from latest changeset args.targets, or args.gate.targets.
    - Records a changeset event: change_control.autosmoke (target_type=change, target_id=change_id)
    """
    store = _store()
    scheduler = _job_scheduler()
    if not store or not scheduler:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    actor0 = actor_from_http(http_request, None)
    tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
    actor_id = actor0.get("actor_id") or http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

    cc = await store.get_change_control(change_id=str(change_id), limit=50, offset=0, tenant_id=tenant_id)
    latest = cc.get("latest") if isinstance(cc, dict) else None
    latest_args = (latest or {}).get("args") if isinstance(latest, dict) else None
    latest_args = latest_args if isinstance(latest_args, dict) else {}

    targets_raw = latest_args.get("targets")
    if not isinstance(targets_raw, list):
        gate = latest_args.get("gate") if isinstance(latest_args.get("gate"), dict) else {}
        targets_raw = gate.get("targets") if isinstance(gate.get("targets"), list) else []

    targets: list[tuple[str, str]] = []
    for t in targets_raw or []:
        if not isinstance(t, dict):
            continue
        ttype = str(t.get("type") or "").strip().lower()
        tid = str(t.get("id") or "").strip()
        if not ttype or not tid:
            continue
        if ttype not in {"agent", "skill", "mcp"}:
            continue
        targets.append((ttype, tid))
    # unique preserve order
    seen = set()
    uniq: list[tuple[str, str]] = []
    for t in targets:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)

    from core.harness.smoke import enqueue_autosmoke

    results: list[Dict[str, Any]] = []
    wam, wsm, wmm = _workspace_managers()
    for rtype, rid in uniq:
        try:
            await mark_resource_pending(resource_type=rtype, resource_id=rid, workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)
        except Exception:
            pass

        async def _on_complete(job_run: Dict[str, Any], *, _rtype=rtype, _rid=rid):
            await apply_autosmoke_result(
                resource_type=_rtype,
                resource_id=_rid,
                job_run=job_run,
                workspace_agent_manager=wam,
                workspace_skill_manager=wsm,
                workspace_mcp_manager=wmm,
            )
            # best-effort: append a changeset event that carries run_id/trace_id for deep linking
            try:
                st = str((job_run or {}).get("status") or "")
                rid2 = str((job_run or {}).get("run_id") or (job_run or {}).get("id") or "") or None
                tid2 = str((job_run or {}).get("trace_id") or "") or None
                await record_changeset(
                    store=store,
                    name="change_control.autosmoke.result",
                    target_type="change",
                    target_id=str(change_id),
                    status="success" if st == "completed" else ("failed" if st else "success"),
                    args={"resource": {"type": _rtype, "id": _rid}},
                    result={"job_run_status": st, "job_run_id": rid2, "job_trace_id": tid2},
                    trace_id=tid2,
                    run_id=rid2,
                    user_id=str(actor0.get("actor_id") or "admin"),
                    tenant_id=str(tenant_id) if tenant_id else None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception:
                pass

        try:
            res = await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=scheduler,
                resource_type=rtype,
                resource_id=rid,
                tenant_id=str(tenant_id or "ops_smoke"),
                actor_id=str(actor_id or "admin"),
                detail={"op": "change_control_retry", "change_id": str(change_id)},
                on_complete=_on_complete,
            )
            results.append({"type": rtype, "id": rid, **(res or {})})
        except Exception as e:
            results.append({"type": rtype, "id": rid, "enqueued": False, "reason": f"error:{e}"})

    try:
        await record_changeset(
            store=store,
            name="change_control.autosmoke",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"targets": [{"type": t[0], "id": t[1]} for t in uniq]},
            result={"results": results},
            user_id=str(actor0.get("actor_id") or "admin"),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
    except Exception:
        pass

    return {"status": "ok", "change_id": str(change_id), "targets": [{"type": t[0], "id": t[1]} for t in uniq], "results": results}


@router.post("/change-control/changes/{change_id}/apply-engine-skill-md-patch")
async def apply_engine_skill_md_patch(change_id: str, http_request: Request):
    """
    Apply an engine SKILL.md patch proposed by skill-eval change-control (sync run_job_once).
    Creates a dedicated job and runs it once (best-effort).
    """
    store = _store()
    scheduler = _job_scheduler()
    if not store or not scheduler:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    actor0 = actor_from_http(http_request, None)
    tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID")
    actor_id = actor0.get("actor_id") or http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

    # Ensure the change exists and contains a proposed patch event.
    cc = await store.get_change_control(change_id=str(change_id), limit=200, offset=0, tenant_id=tenant_id)
    latest = cc.get("latest") if isinstance(cc, dict) else None
    if not isinstance(latest, dict):
        raise HTTPException(status_code=404, detail="change_not_found")
    ev = (cc.get("events") or {}).get("items") if isinstance(cc.get("events"), dict) else None
    ev = ev if isinstance(ev, list) else []
    has_proposed = any(isinstance(it, dict) and str(it.get("name") or "") == "skill_eval.engine_skill_md_patch_proposed" for it in ev)
    if not has_proposed:
        raise HTTPException(status_code=400, detail="unsupported_change_type")

    # Governance gate: support autosmoke/approval policies.
    # NOTE: gate_policy/require_* may be overridden by gate_policy_id later (productization).
    gate_policy = ""
    require_autosmoke = True
    require_approval = False

    # Load events once for gate checks (fail-open on store issues).
    events = []
    try:
        ev_raw = await store.list_syscall_events(limit=400, offset=0, tenant_id=tenant_id, kind="changeset", target_type="change", target_id=str(change_id))
        events = [it for it in (ev_raw.get("items") or []) if isinstance(it, dict)]
    except Exception:
        events = []

    # Helper: get proposed patch payload (skill_eval.engine_skill_md_patch_proposed)
    proposed_event = None
    for it in events:
        if str(it.get("name") or "") == "skill_eval.engine_skill_md_patch_proposed":
            proposed_event = it
            break
    proposed_args = proposed_event.get("args") if isinstance(proposed_event, dict) and isinstance(proposed_event.get("args"), dict) else {}
    proposed_result = proposed_event.get("result") if isinstance(proposed_event, dict) and isinstance(proposed_event.get("result"), dict) else {}

    # ----------------------------
    # Code Intel report (productized)
    # ----------------------------
    try:
        from pathlib import Path

        from core.api.routers.code_intel import _blast as _code_intel_blast  # type: ignore
        from core.api.routers.code_intel import _default_roots as _code_intel_default_roots  # type: ignore
        from core.api.routers.code_intel import _get_scan as _code_intel_get_scan  # type: ignore
        from core.api.routers.code_intel import _repo_root as _code_intel_repo_root  # type: ignore

        raw_path = proposed_result.get("path")
        raw_path = str(raw_path) if isinstance(raw_path, str) else ""
        repo_root = _code_intel_repo_root()
        rel_candidates: list[str] = []
        if raw_path:
            # best-effort normalize into repo-relative path (aiPlat-core/... or aiPlat-management/...)
            p0 = Path(raw_path).resolve()
            try:
                rel_candidates.append(str(p0.relative_to(repo_root)).replace("\\", "/"))
            except Exception:
                s = str(p0).replace("\\", "/")
                for marker in ["/aiPlat-core/", "/aiPlat-management/"]:
                    if marker in s:
                        rel_candidates.append(s.split(marker, 1)[1])
                        rel_candidates[-1] = ("aiPlat-core/" + rel_candidates[-1]) if marker == "/aiPlat-core/" else ("aiPlat-management/" + rel_candidates[-1])
                        break
        roots0 = _code_intel_default_roots()
        scan = await _code_intel_get_scan(get_kernel_runtime(), roots0)
        touched = []
        for rel in [x for x in rel_candidates if x]:
            exists_in_graph = rel in scan.nodes
            blast = _code_intel_blast(scan.nodes, rel) if exists_in_graph else []
            touched.append(
                {
                    "file": rel,
                    "in_graph": bool(exists_in_graph),
                    "blast_count": len(blast),
                    "blast_top": blast[:50],
                }
            )
        await record_changeset(
            store=store,
            name="code_intel.report",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"roots": roots0, "source_path": raw_path, "files": rel_candidates},
            result={"stats": scan.stats, "touched": touched, "notes": "server-side heuristic import graph (CodeFlow-inspired)"},
            user_id=str(actor_id or "admin"),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
    except Exception:
        # fail open: code intel should never block apply flow
        pass

    # ----------------------------
    # Gate Policy (productized)
    # ----------------------------
    def _load_gate_policy_config_sync(value: Dict[str, Any], *, policy_id: str) -> Optional[Dict[str, Any]]:
        items = value.get("items") if isinstance(value.get("items"), list) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("policy_id") or "") == str(policy_id):
                cfg = it.get("config") if isinstance(it.get("config"), dict) else {}
                return cfg if isinstance(cfg, dict) else {}
        return None

    gate_policy_id = (http_request.query_params.get("gate_policy_id") or "").strip()
    gate_policy_source = "none"
    gate_policy_cfg: Dict[str, Any] = {}
    try:
        gs = await store.get_global_setting(key="gate_policies")
        v = (gs or {}).get("value") if isinstance(gs, dict) else None
        v = v if isinstance(v, dict) else {}
        if not gate_policy_id:
            # default selection
            did = str(v.get("default_id") or "").strip()
            if did:
                gate_policy_id = did
                gate_policy_source = "default"
        if gate_policy_id:
            cfg0 = _load_gate_policy_config_sync(v, policy_id=gate_policy_id)
            if isinstance(cfg0, dict):
                gate_policy_cfg = cfg0
                if gate_policy_source == "none":
                    gate_policy_source = "query"
    except Exception:
        gate_policy_cfg = {}

    def _apply_api_path() -> str:
        base = f"/api/core/change-control/changes/{str(change_id)}/apply-engine-skill-md-patch"
        if gate_policy_id:
            return base + f"?gate_policy_id={str(gate_policy_id)}"
        return base

    # Resolve params with precedence: query params override gate_policy config.
    # apply gate
    gate_policy = (http_request.query_params.get("gate_policy") or "").strip().lower()
    if not gate_policy:
        try:
            gate_policy = str(((gate_policy_cfg.get("apply_gate") or {}).get("gate_policy") or "")).strip().lower()
        except Exception:
            gate_policy = ""
    if gate_policy not in {"autosmoke", "approval", "any", "all"}:
        gate_policy = (os.getenv("AIPLAT_ENGINE_SKILL_PATCH_APPLY_GATE", "autosmoke") or "autosmoke").strip().lower()
    if gate_policy not in {"autosmoke", "approval", "any", "all"}:
        gate_policy = "autosmoke"

    require_autosmoke = gate_policy in {"autosmoke", "any", "all"}
    require_approval = gate_policy in {"approval", "any", "all"}
    # Optional explicit toggles inside gate policy config.
    try:
        ag = gate_policy_cfg.get("apply_gate") if isinstance(gate_policy_cfg.get("apply_gate"), dict) else {}
        if isinstance(ag.get("require_autosmoke"), bool):
            require_autosmoke = bool(ag.get("require_autosmoke"))
        if isinstance(ag.get("require_approval"), bool):
            require_approval = bool(ag.get("require_approval"))
    except Exception:
        pass
    # Backward-compatible query overrides:
    try:
        raw = (http_request.query_params.get("require_autosmoke") or "").strip().lower()
        if raw in {"0", "false", "no", "n"}:
            require_autosmoke = False
        if raw in {"1", "true", "yes", "y"}:
            require_autosmoke = True
    except Exception:
        pass
    try:
        raw = (http_request.query_params.get("require_approval") or "").strip().lower()
        if raw in {"0", "false", "no", "n"}:
            require_approval = False
        if raw in {"1", "true", "yes", "y"}:
            require_approval = True
    except Exception:
        pass
    # Env safety rails:
    try:
        env = (os.getenv("AIPLAT_REQUIRE_AUTOSMOKE_FOR_ENGINE_SKILL_PATCH", "true") or "true").strip().lower()
        if env in {"0", "false", "no", "n"}:
            require_autosmoke = False
    except Exception:
        pass
    try:
        env = (os.getenv("AIPLAT_REQUIRE_APPROVAL_FOR_ENGINE_SKILL_PATCH", "false") or "false").strip().lower()
        if env in {"1", "true", "yes", "y"}:
            require_approval = True
    except Exception:
        pass

    # Resolve non-executing gate parameters early so they can be recorded even if a gate fails later.
    # Eval gate (mode + suite ids + thresholds)
    eval_gate = (http_request.query_params.get("eval_gate") or "").strip().lower()
    if not eval_gate:
        try:
            eval_gate = str(((gate_policy_cfg.get("eval_gate") or {}).get("mode") or "off")).strip().lower()
        except Exception:
            eval_gate = "off"
    if eval_gate not in {"off", "trigger", "trigger+quality"}:
        eval_gate = "off"
    trigger_suite_id = (http_request.query_params.get("trigger_suite_id") or "").strip()
    if not trigger_suite_id:
        trigger_suite_id = str(((gate_policy_cfg.get("eval_gate") or {}).get("trigger_suite_id") or proposed_args.get("suite_id") or "")).strip()
    quality_suite_id = (http_request.query_params.get("quality_suite_id") or "").strip()
    if not quality_suite_id:
        quality_suite_id = str(((gate_policy_cfg.get("eval_gate") or {}).get("quality_suite_id") or "")).strip()
    try:
        trigger_f1_min = float(http_request.query_params.get("trigger_f1_min") or ((gate_policy_cfg.get("eval_gate") or {}).get("trigger_f1_min")) or "0.5")
    except Exception:
        trigger_f1_min = 0.5
    try:
        quality_pass_rate_min = float(http_request.query_params.get("quality_pass_rate_min") or ((gate_policy_cfg.get("eval_gate") or {}).get("quality_pass_rate_min")) or "0.9")
    except Exception:
        quality_pass_rate_min = 0.9

    # Security gate (mode only; scanning happens later)
    security_gate = (http_request.query_params.get("security_gate") or "").strip().lower()
    if not security_gate:
        try:
            security_gate = str(((gate_policy_cfg.get("security_gate") or {}).get("mode") or "off")).strip().lower()
        except Exception:
            security_gate = "off"
    if security_gate not in {"off", "scan_warn", "scan_block"}:
        security_gate = "off"

    # Record resolved gate policy (best-effort; for UI + evidence).
    # Do this BEFORE any gate may fail so users can always see what was applied.
    try:
        if gate_policy_id:
            await record_changeset(
                store=store,
                name="gate_policy.resolved",
                target_type="change",
                target_id=str(change_id),
                status="success",
                args={"gate_policy_id": str(gate_policy_id), "source": gate_policy_source},
                result={
                    "resolved": {
                        "apply_gate": {"gate_policy": gate_policy, "require_autosmoke": require_autosmoke, "require_approval": require_approval},
                        "eval_gate": {
                            "mode": eval_gate,
                            "trigger_suite_id": trigger_suite_id,
                            "quality_suite_id": quality_suite_id,
                            "trigger_f1_min": trigger_f1_min,
                            "quality_pass_rate_min": quality_pass_rate_min,
                        },
                        "security_gate": {"mode": security_gate},
                    }
                },
                user_id=str(actor_id or "admin"),
                tenant_id=str(tenant_id) if tenant_id else None,
                session_id=str(actor0.get("session_id") or "") or None,
            )
    except Exception:
        pass

    autosmoke_ok = False
    if require_autosmoke:
        try:
            for it in events:
                if str(it.get("name") or "") != "change_control.autosmoke.result":
                    continue
                res = it.get("result") if isinstance(it.get("result"), dict) else {}
                st = str(res.get("job_run_status") or "")
                if st == "completed":
                    autosmoke_ok = True
                    break
        except Exception:
            autosmoke_ok = False

    approval_ok = False
    approval_request_id = None
    if require_approval:
        try:
            # Prefer approval_request_id attached to the proposed patch changeset.
            for it in events:
                if str(it.get("name") or "") == "skill_eval.engine_skill_md_patch_proposed" and str(it.get("approval_request_id") or "").strip():
                    approval_request_id = str(it.get("approval_request_id")).strip()
                    break
            if not approval_request_id:
                for it in events:
                    if str(it.get("approval_request_id") or "").strip():
                        approval_request_id = str(it.get("approval_request_id")).strip()
                        break
            if approval_request_id:
                rec = await store.get_approval_request(str(approval_request_id))
                st = str((rec or {}).get("status") or "").strip().lower()
                if st in {"approved", "auto_approved"}:
                    approval_ok = True
        except Exception:
            approval_ok = False

    gate_pass = True
    if gate_policy == "autosmoke":
        gate_pass = (not require_autosmoke) or autosmoke_ok
    elif gate_policy == "approval":
        gate_pass = (not require_approval) or approval_ok
    elif gate_policy == "all":
        gate_pass = ((not require_autosmoke) or autosmoke_ok) and ((not require_approval) or approval_ok)
    else:  # any
        gate_pass = ((require_autosmoke and autosmoke_ok) or (require_approval and approval_ok) or (not require_autosmoke and not require_approval))

    if not gate_pass:
        next_actions = []
        links = governance_links(change_id=str(change_id), approval_request_id=str(approval_request_id) if approval_request_id else None)
        missing_approval = bool(require_approval and not approval_ok)
        missing_autosmoke = bool(require_autosmoke and not autosmoke_ok)
        # Recommend the shortest/most actionable next step for UI defaults.
        recommended_type = None
        if missing_approval and approval_request_id:
            recommended_type = "approve"
        elif missing_autosmoke:
            recommended_type = "autosmoke"
        else:
            recommended_type = "retry"
        if require_approval and not approval_ok:
            if approval_request_id:
                next_actions.append(
                    {
                        "type": "approve",
                        "label": "审批该请求",
                        "request_id": str(approval_request_id),
                        "api": {"method": "POST", "path": f"/api/core/approvals/{str(approval_request_id)}/approve"},
                        "ui": links.get("approvals_ui"),
                        "recommended": True if recommended_type == "approve" else False,
                    }
                )
            else:
                next_actions.append({"type": "open_ui", "label": "打开审批列表", "ui": links.get("approvals_ui"), "recommended": True if recommended_type == "approve" else False})
        if require_autosmoke and not autosmoke_ok:
            next_actions.append(
                {
                    "type": "autosmoke",
                    "label": "运行自动冒烟",
                    "api": {"method": "POST", "path": f"/api/core/change-control/changes/{str(change_id)}/autosmoke"},
                    "ui": links.get("change_control_ui"),
                    "recommended": True if recommended_type == "autosmoke" else False,
                }
            )
        next_actions.append(
            {
                "type": "retry",
                "label": "重试应用",
                "api": {"method": "POST", "path": _apply_api_path()},
                "recommended": True if recommended_type == "retry" else False,
            }
        )
        # Sort: recommended first (stable), then others.
        try:
            next_actions.sort(key=lambda x: (0 if x.get("recommended") else 1))
        except Exception:
            pass
        # Record a failure event for UI observability (best-effort)
        try:
            await record_changeset(
                store=store,
                name="apply_gate.failed",
                target_type="change",
                target_id=str(change_id),
                status="failed",
                args={
                    "gate_policy_id": str(gate_policy_id) if gate_policy_id else None,
                    "gate_policy": gate_policy,
                    "require_autosmoke": require_autosmoke,
                    "require_approval": require_approval,
                },
                result={
                    "autosmoke_ok": autosmoke_ok,
                    "approval_ok": approval_ok,
                    "approval_request_id": approval_request_id,
                    "links": links,
                    "next_actions": next_actions,
                    "recommended_next_action": recommended_type,
                },
                user_id=str(actor_id or "admin"),
                tenant_id=str(tenant_id) if tenant_id else None,
                session_id=str(actor0.get("session_id") or "") or None,
                approval_request_id=str(approval_request_id) if approval_request_id else None,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail=gate_error_envelope(
                code="apply_gate_failed",
                message="apply_gate_failed",
                change_id=str(change_id),
                approval_request_id=str(approval_request_id) if approval_request_id else None,
                links=links,
                next_actions=next_actions,
                detail={
                    "gate_policy": gate_policy,
                    "autosmoke_ok": autosmoke_ok,
                    "approval_ok": approval_ok,
                    "require_autosmoke": require_autosmoke,
                    "require_approval": require_approval,
                    "recommended_next_action": recommended_type,
                },
            ),
        )

    # ----------------------------
    # Eval gate (trigger/quality)
    # ----------------------------

    def _has_changeset(name: str) -> Optional[Dict[str, Any]]:
        for it in events:
            if str(it.get("name") or "") == name:
                return it
        return None

    async def _run_eval_skill(*, skill_id: str, suite_id: str, job_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # Create/update an ad-hoc job and run once
        job = await store.get_job(job_id)
        payload = {"input": input_data, "context": {"tenant_id": tenant_id}}
        if job is None:
            await store.create_job(
                {
                    "id": job_id,
                    "name": f"Gate eval {skill_id} for {change_id}",
                    "enabled": False,
                    "cron": "0 0 1 1 *",
                    "kind": "skill",
                    "target_id": skill_id,
                    "user_id": str(actor_id or "system"),
                    "session_id": str(tenant_id or "ops"),
                    "payload": payload,
                }
            )
        else:
            await store.update_job(job_id, {"payload": payload, "user_id": str(actor_id or "system"), "session_id": str(tenant_id or "ops")})
        return await scheduler.run_job_once(job_id)

    async def _ensure_trigger_eval():
        if not trigger_suite_id:
            return {"ok": False, "reason": "missing_trigger_suite_id"}
        existing = _has_changeset("skill_eval.gate.trigger_eval")
        if existing:
            res0 = existing.get("result") if isinstance(existing.get("result"), dict) else {}
            return {"ok": bool(res0.get("passed", False)), "cached": True, "result": res0}
        job_id = f"gate-eval-trigger:{str(change_id)}"
        job_run = await _run_eval_skill(
            skill_id="skill_eval_trigger",
            suite_id=trigger_suite_id,
            job_id=job_id,
            input_data={"suite_id": trigger_suite_id, "mode": "heuristic", "max_cases": 200},
        )
        # parse eval run id (best-effort; support multiple payload shapes)
        payload_out = (job_run or {}).get("result", {}).get("payload") if isinstance((job_run or {}).get("result"), dict) else None
        def _find_run_id(x: Any) -> Optional[str]:
            if isinstance(x, dict):
                if isinstance(x.get("run_id"), str) and x.get("run_id"):
                    return x.get("run_id")
                for k in ("output", "result", "payload", "data"):
                    v = x.get(k)
                    rid = _find_run_id(v)
                    if rid:
                        return rid
            elif isinstance(x, list):
                for it in x[:10]:
                    rid = _find_run_id(it)
                    if rid:
                        return rid
            return None
        eval_run_id = _find_run_id(payload_out)
        metrics = None
        # fail closed: if job failed or we can't obtain eval_run_id, treat as gate failure
        passed = True
        try:
            if str((job_run or {}).get("status") or "") != "completed":
                passed = False
        except Exception:
            passed = False
        if not eval_run_id:
            passed = False
        if eval_run_id:
            rr = await store.get_skill_eval_run(run_id=str(eval_run_id))
            metrics = rr.get("metrics") if isinstance(rr, dict) else None
            if not rr or not isinstance(metrics, dict):
                passed = False
            try:
                f1 = float((metrics or {}).get("f1")) if isinstance(metrics, dict) and (metrics or {}).get("f1") is not None else None
            except Exception:
                f1 = None
            if f1 is None:
                passed = False
            elif f1 < float(trigger_f1_min):
                passed = False
        await record_changeset(
            store=store,
            name="skill_eval.gate.trigger_eval",
            target_type="change",
            target_id=str(change_id),
            status="success" if passed else "failed",
            args={"suite_id": trigger_suite_id, "trigger_f1_min": trigger_f1_min},
            result={"passed": passed, "eval_run_id": eval_run_id, "metrics": metrics, "job_run": job_run},
            user_id=str(actor_id or "admin"),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
        return {"ok": passed, "cached": False, "eval_run_id": eval_run_id, "metrics": metrics}

    async def _ensure_quality_eval():
        if not quality_suite_id:
            return {"ok": True, "skipped": True}
        existing = _has_changeset("skill_eval.gate.quality_eval")
        if existing:
            res0 = existing.get("result") if isinstance(existing.get("result"), dict) else {}
            return {"ok": bool(res0.get("passed", False)), "cached": True, "result": res0}
        job_id = f"gate-eval-quality:{str(change_id)}"
        job_run = await _run_eval_skill(
            skill_id="skill_eval_quality",
            suite_id=quality_suite_id,
            job_id=job_id,
            input_data={"suite_id": quality_suite_id, "max_cases": 50},
        )
        payload_out = (job_run or {}).get("result", {}).get("payload") if isinstance((job_run or {}).get("result"), dict) else None
        def _find_run_id(x: Any) -> Optional[str]:
            if isinstance(x, dict):
                if isinstance(x.get("run_id"), str) and x.get("run_id"):
                    return x.get("run_id")
                for k in ("output", "result", "payload", "data"):
                    v = x.get(k)
                    rid = _find_run_id(v)
                    if rid:
                        return rid
            elif isinstance(x, list):
                for it in x[:10]:
                    rid = _find_run_id(it)
                    if rid:
                        return rid
            return None
        eval_run_id = _find_run_id(payload_out)
        metrics = None
        passed = True
        try:
            if str((job_run or {}).get("status") or "") != "completed":
                passed = False
        except Exception:
            passed = False
        if not eval_run_id:
            passed = False
        if eval_run_id:
            rr = await store.get_skill_eval_run(run_id=str(eval_run_id))
            metrics = rr.get("metrics") if isinstance(rr, dict) else None
            if not rr or not isinstance(metrics, dict):
                passed = False
            try:
                pr = float((metrics or {}).get("pass_rate")) if isinstance(metrics, dict) and (metrics or {}).get("pass_rate") is not None else None
            except Exception:
                pr = None
            if pr is None:
                passed = False
            elif pr < float(quality_pass_rate_min):
                passed = False
        await record_changeset(
            store=store,
            name="skill_eval.gate.quality_eval",
            target_type="change",
            target_id=str(change_id),
            status="success" if passed else "failed",
            args={"suite_id": quality_suite_id, "quality_pass_rate_min": quality_pass_rate_min},
            result={"passed": passed, "eval_run_id": eval_run_id, "metrics": metrics, "job_run": job_run},
            user_id=str(actor_id or "admin"),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
        return {"ok": passed, "cached": False, "eval_run_id": eval_run_id, "metrics": metrics}

    if eval_gate != "off":
        # Run trigger eval gate
        trig = await _ensure_trigger_eval()
        if not trig.get("ok", False):
            links = governance_links(change_id=str(change_id))
            next_actions = [
                {"type": "open_ui", "label": "查看变更详情", "ui": links.get("change_control_ui"), "recommended": True},
                {"type": "retry", "label": "重试应用", "api": {"method": "POST", "path": _apply_api_path()}},
            ]
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="eval_gate_failed",
                    message="Trigger Eval gate failed",
                    change_id=str(change_id),
                    links=links,
                    next_actions=next_actions,
                    detail={"eval_gate": eval_gate, "trigger_suite_id": trigger_suite_id, "trigger_f1_min": trigger_f1_min, "trigger_eval": trig},
                ),
            )
        # Optionally run quality eval gate
        if eval_gate == "trigger+quality":
            q = await _ensure_quality_eval()
            if not q.get("ok", False):
                links = governance_links(change_id=str(change_id))
                next_actions = [
                    {"type": "open_ui", "label": "查看变更详情", "ui": links.get("change_control_ui"), "recommended": True},
                    {"type": "retry", "label": "重试应用", "api": {"method": "POST", "path": _apply_api_path()}},
                ]
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="eval_gate_failed",
                        message="Quality Eval gate failed",
                        change_id=str(change_id),
                        links=links,
                        next_actions=next_actions,
                        detail={"eval_gate": eval_gate, "quality_suite_id": quality_suite_id, "quality_pass_rate_min": quality_pass_rate_min, "quality_eval": q},
                    ),
                )

    # ----------------------------
    # Security scan gate (warn/block)
    # ----------------------------
    if security_gate != "off":
        existing = _has_changeset("skill_eval.gate.security_scan")
        scan_res = None
        passed = True
        if existing:
            scan_res = existing.get("result") if isinstance(existing.get("result"), dict) else {}
            passed = bool(scan_res.get("passed", True))
        else:
            try:
                from core.apps.quality.scanner import create_security_scanner
                from core.apps.quality.types import VulnerabilitySeverity

                scanner = create_security_scanner(severity_threshold=VulnerabilitySeverity.MEDIUM)
                updated_raw = proposed_result.get("updated_raw") if isinstance(proposed_result, dict) else None
                updated_raw = str(updated_raw or "")
                scan = await scanner.scan(updated_raw, context={"file": proposed_result.get("path") or "SKILL.md"})
                # passed means no HIGH+ per scanner definition
                passed = bool(getattr(scan, "passed", True))
                # serialize
                vulns = []
                try:
                    for v in getattr(scan, "vulnerabilities", []) or []:
                        vulns.append(
                            {
                                "severity": getattr(getattr(v, "severity", None), "value", None),
                                "type": getattr(getattr(v, "type", None), "value", None),
                                "location": getattr(v, "location", None),
                                "description": getattr(v, "description", None),
                                "suggestion": getattr(v, "suggestion", None),
                                "line_number": getattr(v, "line_number", None),
                            }
                        )
                except Exception:
                    vulns = []
                scan_res = {"passed": passed, "vulnerabilities": vulns, "scanned_at": getattr(scan, "scanned_at", None)}
            except Exception as e:
                # Fail-closed for scan_block, fail-open for scan_warn/off.
                scan_res = {"passed": False if security_gate == "scan_block" else True, "error": str(e)}
                passed = False if security_gate == "scan_block" else True
            try:
                await record_changeset(
                    store=store,
                    name="skill_eval.gate.security_scan",
                    target_type="change",
                    target_id=str(change_id),
                    status="success" if passed else "failed",
                    args={"security_gate": security_gate},
                    result=scan_res,
                    user_id=str(actor_id or "admin"),
                    tenant_id=str(tenant_id) if tenant_id else None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception:
                pass
        if security_gate == "scan_block" and not passed:
            links = governance_links(change_id=str(change_id))
            next_actions = [
                {"type": "open_ui", "label": "查看变更详情", "ui": links.get("change_control_ui"), "recommended": True},
                {"type": "retry", "label": "重试应用", "api": {"method": "POST", "path": _apply_api_path()}},
            ]
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="security_gate_failed",
                    message="Security scan gate failed",
                    change_id=str(change_id),
                    links=links,
                    next_actions=next_actions,
                    detail={"security_gate": security_gate, "scan": scan_res},
                ),
            )

    job_id = f"apply-engine-skill-md:{str(change_id)}"
    job = await store.get_job(job_id)
    if job is None:
        # disabled cron; run manually
        job = await store.create_job(
            {
                "id": job_id,
                "name": f"Apply engine skill md patch {str(change_id)}",
                "enabled": False,
                "cron": "0 0 1 1 *",
                "kind": "skill",
                "target_id": "skill_apply_engine_skill_md_patch",
                "user_id": str(actor_id or "system"),
                "session_id": str(tenant_id or "ops"),
                "payload": {"input": {"change_id": str(change_id)}, "context": {"tenant_id": tenant_id}},
            }
        )
    else:
        await store.update_job(job_id, {"user_id": str(actor_id or "system"), "session_id": str(tenant_id or "ops"), "payload": {"input": {"change_id": str(change_id)}, "context": {"tenant_id": tenant_id}}})

    # Run immediately (sync)
    run = await scheduler.run_job_once(job_id)
    return {"status": "ok", "change_id": str(change_id), "job_id": job_id, "job_run": run}


@router.get("/change-control/changes/{change_id}/evidence")
async def export_change_control_evidence(change_id: str, http_request: Request, format: str = "zip", limit: int = 500):
    """
    Export an evidence pack for a change_id.
    format:
      - json: returns a JSON object
      - zip: returns a ZIP containing evidence.json
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    fmt = str(format or "zip").strip().lower()
    if fmt not in {"json", "zip"}:
        raise HTTPException(status_code=400, detail="format must be json|zip")

    tenant_id = None
    try:
        actor0 = actor_from_http(http_request, None)
        tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID")
    except Exception:
        tenant_id = None

    cc = await store.get_change_control(change_id=str(change_id), limit=int(limit), offset=0, tenant_id=tenant_id)
    cc["links"] = {
        "change_control_ui": ui_url(f"/diagnostics/change-control/{str(change_id)}"),
        "syscalls_ui": ui_url(f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={str(change_id)}"),
        "audit_ui": ui_url(f"/diagnostics/audit?change_id={str(change_id)}"),
    }

    audits = await store.list_audit_logs(change_id=str(change_id), limit=1000, offset=0)
    summary = cc.get("summary") if isinstance(cc, dict) else None
    latest_run_id = None
    try:
        if isinstance(summary, dict):
            latest_run_id = summary.get("latest_run_id")
        if not latest_run_id and isinstance(cc.get("latest"), dict):
            latest_run_id = cc["latest"].get("run_id")
    except Exception:
        latest_run_id = None

    run = None
    run_events = None
    if latest_run_id:
        try:
            run = await store.get_run_summary(run_id=str(latest_run_id))
        except Exception:
            run = None
        try:
            run_events = await store.list_run_events(run_id=str(latest_run_id), after_seq=0, limit=500)
        except Exception:
            run_events = None

    evidence = {"change_id": str(change_id), "exported_at": time.time(), "change_control": cc, "audit": audits, "run": run, "run_events": run_events}

    def _pick_event(name: str) -> Optional[Dict[str, Any]]:
        try:
            items = (cc.get("events") or {}).get("items") if isinstance(cc.get("events"), dict) else None
            items = items if isinstance(items, list) else []
            for it in items:
                if isinstance(it, dict) and str(it.get("name") or "") == name:
                    return it
        except Exception:
            return None
        return None

    proposed = _pick_event("skill_eval.engine_skill_md_patch_proposed")
    applied = _pick_event("skill_eval.engine_skill_md_patch_applied")
    autosmoke = _pick_event("change_control.autosmoke.result")
    trig_gate = _pick_event("skill_eval.gate.trigger_eval")
    qual_gate = _pick_event("skill_eval.gate.quality_eval")
    sec_gate = _pick_event("skill_eval.gate.security_scan")
    gate_policy_ev = _pick_event("gate_policy.resolved")
    apply_gate_failed = _pick_event("apply_gate.failed")
    code_intel_ev = _pick_event("code_intel.report")

    approval_request_id = None
    try:
        approval_request_id = (cc.get("latest") or {}).get("approval_request_id") if isinstance(cc.get("latest"), dict) else None
        if not approval_request_id and isinstance(proposed, dict):
            approval_request_id = proposed.get("approval_request_id")
    except Exception:
        approval_request_id = None

    summary_json = {
        "change_id": str(change_id),
        "status": "applied" if applied else ("proposed" if proposed else "unknown"),
        "proposed": {
            "at": proposed.get("created_at") if isinstance(proposed, dict) else None,
            "skill_id": (proposed.get("args") or {}).get("skill_id") if isinstance(proposed, dict) else None,
            "suite_id": (proposed.get("args") or {}).get("suite_id") if isinstance(proposed, dict) else None,
            "diff_hash": (proposed.get("args") or {}).get("diff_hash") if isinstance(proposed, dict) else None,
            "base_hash": (proposed.get("args") or {}).get("base_hash") if isinstance(proposed, dict) else None,
            "path": (proposed.get("result") or {}).get("path") if isinstance(proposed, dict) else None,
        },
        "applied": {"at": applied.get("created_at") if isinstance(applied, dict) else None} if applied else None,
        "approval": {"request_id": approval_request_id} if approval_request_id else None,
        "autosmoke": (autosmoke.get("result") if isinstance(autosmoke, dict) else None),
        "gate_policy": (gate_policy_ev.get("result") if isinstance(gate_policy_ev, dict) else None),
        "code_intel": (code_intel_ev.get("result") if isinstance(code_intel_ev, dict) else None),
        "gates": {
            "apply_gate": (apply_gate_failed.get("result") if isinstance(apply_gate_failed, dict) else None),
            "trigger_eval": (trig_gate.get("result") if isinstance(trig_gate, dict) else None),
            "quality_eval": (qual_gate.get("result") if isinstance(qual_gate, dict) else None),
            "security_scan": (sec_gate.get("result") if isinstance(sec_gate, dict) else None),
        },
        "links": (cc.get("links") if isinstance(cc.get("links"), dict) else {}),
    }

    # Human-readable summary (best-effort)
    def _ok_bad(x: Any) -> str:
        return "✅" if x else "❌"

    trig_pass = None
    try:
        trig_pass = (summary_json["gates"]["trigger_eval"] or {}).get("passed")
    except Exception:
        trig_pass = None
    qual_pass = None
    try:
        qual_pass = (summary_json["gates"]["quality_eval"] or {}).get("passed")
    except Exception:
        qual_pass = None
    sec_pass = None
    try:
        sec_pass = (summary_json["gates"]["security_scan"] or {}).get("passed")
    except Exception:
        sec_pass = None
    autosmoke_ok = None
    try:
        autosmoke_ok = (summary_json.get("autosmoke") or {}).get("job_run_status") == "completed"
    except Exception:
        autosmoke_ok = None

    summary_md = "\n".join(
        [
            f"# Change Evidence Summary: {str(change_id)}",
            "",
            f"- 状态：{summary_json.get('status')}",
            f"- Skill：{summary_json.get('proposed', {}).get('skill_id')}",
            f"- Suite：{summary_json.get('proposed', {}).get('suite_id')}",
            f"- Diff Hash：{summary_json.get('proposed', {}).get('diff_hash')}",
            f"- Base Hash：{summary_json.get('proposed', {}).get('base_hash')}",
            "",
            "## Gate 结果",
            f"- Autosmoke：{_ok_bad(autosmoke_ok) if autosmoke_ok is not None else 'N/A'}",
            f"- Trigger Eval：{_ok_bad(trig_pass) if trig_pass is not None else 'N/A'}",
            f"- Quality Eval：{_ok_bad(qual_pass) if qual_pass is not None else 'N/A'}",
            f"- Security Scan：{_ok_bad(sec_pass) if sec_pass is not None else 'N/A'}",
            "",
            "## Links",
            f"- Change Control UI: {(summary_json.get('links') or {}).get('change_control_ui')}",
            f"- Syscalls UI: {(summary_json.get('links') or {}).get('syscalls_ui')}",
            f"- Audit UI: {(summary_json.get('links') or {}).get('audit_ui')}",
        ]
    )

    evidence["summary"] = summary_json
    if fmt == "json":
        return evidence

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
        zf.writestr("summary.json", json.dumps(summary_json, ensure_ascii=False, indent=2, default=str))
        zf.writestr("summary.md", summary_md)
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="change_{str(change_id)}_evidence.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
