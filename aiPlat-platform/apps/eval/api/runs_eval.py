from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http, rbac_guard
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.integration import KernelRuntime
from core.schemas_eval import EvidenceDiffRequest

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt):
    return getattr(rt, "execution_store", None) if rt else None

def _mcp_mgr(rt):
    return getattr(rt, "mcp_manager", None) if rt else None

def _workspace_mcp_mgr(rt):
    return getattr(rt, "workspace_mcp_manager", None) if rt else None


# ════════════════════════════════════════════════════════════════════════
# Evaluation endpoints (migrated from runs.py)
# ════════════════════════════════════════════════════════════════════════

@router.post("/runs/{run_id}/evaluate", response_model=Dict[str, Any])
async def submit_run_evaluation(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """Accept structured evaluator report JSON, apply threshold gate, persist."""
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
    try:
        if isinstance(gated_report, dict) and project_id:
            gated_report.setdefault("project_id", project_id)
        if isinstance(gated_report, dict) and url:
            gated_report.setdefault("url", url)
        if isinstance(gated_report, dict) and base_evidence_pack_id_req:
            gated_report.setdefault("base_evidence_pack_id", base_evidence_pack_id_req)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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
    try:
        from core.harness.restatement.run_state import merge_from_evaluation, normalize_run_state
        from core.learning.manager import LearningManager
        from core.learning.types import LearningArtifactKind

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
        merged = merge_from_evaluation(cur2, evaluation_report=gated_report, source="evaluator")
        await mgr.create_artifact(
            kind=LearningArtifactKind.RUN_STATE,
            target_type="run", target_id=rid,
            version=f"run_state:{int(time.time())}",
            status="draft", payload=merged,
            metadata={"source": "evaluator", "locked": bool(merged.get("locked"))},
            trace_id=run.get("trace_id"), run_id=rid,
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    if enforce_gate and not bool(gated_report.get("pass")):
        raise HTTPException(status_code=409, detail={"code": "evaluation_failed", "artifact_id": saved.get("artifact_id"), "report": gated_report})
    return {"status": "ok", "artifact_id": saved.get("artifact_id"), "report": gated_report}


@router.post("/runs/{run_id}/evaluate/auto", response_model=Dict[str, Any])
async def auto_evaluate_run(run_id: str, http_request: Request, rt: RuntimeDep = None):
    """Auto-collect latest evaluation summary for a run (reads existing data, no LLM)."""
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

    def _latest(items):
        if isinstance(items, list) and items:
            return sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)[0]
        return None

    latest_eval = None
    latest_pack = None
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evaluation_report", limit=10, offset=0)
        latest_eval = _latest((r0 or {}).get("items"))
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_pack", limit=10, offset=0)
        latest_pack = _latest((r0 or {}).get("items"))
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    syscall_summary = {"total": 0, "errors": 0}
    try:
        s0 = await store.list_syscall_events(run_id=rid, limit=200, offset=0)
        items = (s0 or {}).get("items") if isinstance(s0, dict) else []
        if isinstance(items, list):
            errs = [x for x in items if (x or {}).get("error")]
            syscall_summary = {"total": len(items), "errors": len(errs)}
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    return {
        "trace_id": run.get("trace_id"),
        "latest_eval": (latest_eval or {}).get("payload", {}) if isinstance(latest_eval, dict) else {},
        "latest_pack": (latest_pack or {}).get("payload", {}) if isinstance(latest_pack, dict) else {},
        "syscall_summary": syscall_summary,
    }


@router.get("/runs/{run_id}/evaluation/latest", response_model=Dict[str, Any])
async def get_latest_run_evaluation(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evaluation_report", limit=20, offset=0)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.get("/runs/{run_id}/investigate/latest", response_model=Dict[str, Any])
async def get_latest_investigate_report(run_id: str, rt: RuntimeDep = None):
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


@router.post("/runs/{run_id}/investigate/auto", response_model=Dict[str, Any])
async def auto_investigate_run(run_id: str, http_request: Request, rt: RuntimeDep = None):
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

    def _latest(items):
        if isinstance(items, list) and items:
            return sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)[0]
        return None

    latest_eval = None; latest_pack = None; latest_diff = None
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evaluation_report", limit=10, offset=0)
        latest_eval = _latest((r0 or {}).get("items"))
    except Exception:
            logging.getLogger("runs_eval").warning("best-effort skipped", exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_pack", limit=10, offset=0)
        latest_pack = _latest((r0 or {}).get("items"))
    except Exception:
            logging.getLogger("runs_eval").warning("best-effort skipped", exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_diff", limit=10, offset=0)
        latest_diff = _latest((r0 or {}).get("items"))
    except Exception:
            logging.getLogger("runs_eval").warning("best-effort skipped", exc_info=True)

    syscall_items = []
    syscall_summary = {"total": 0, "errors": 0, "top_errors": [], "slow": []}
    try:
        s0 = await store.list_syscall_events(run_id=rid, limit=200, offset=0)
        syscall_items = (s0 or {}).get("items") if isinstance(s0, dict) else []
        if not isinstance(syscall_items, list):
            syscall_items = []
        errs = [x for x in syscall_items if str((x or {}).get("status") or "").lower() not in {"ok", "success"} or (x or {}).get("error")]
        counts = {}
        for e in errs:
            code = str((e or {}).get("error_code") or (e or {}).get("error") or "error").strip()
            counts[code] = counts.get(code, 0) + 1
        top_errors = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        slow = sorted(syscall_items, key=lambda x: float((x or {}).get("duration_ms") or 0), reverse=True)[:10]
        syscall_summary = {"total": len(syscall_items), "errors": len(errs),
            "top_errors": [{"error_code": k, "count": v} for k, v in top_errors],
            "slow": [{"name": (x or {}).get("name"), "kind": (x or {}).get("kind"),
                      "status": (x or {}).get("status"), "duration_ms": (x or {}).get("duration_ms"),
                      "error_code": (x or {}).get("error_code")} for x in slow]}
    except Exception:
            logging.getLogger("runs_eval").warning("best-effort skipped", exc_info=True)

    eval_payload = (latest_eval or {}).get("payload") if isinstance(latest_eval, dict) else {}
    pack_payload = (latest_pack or {}).get("payload") if isinstance(latest_pack, dict) else {}
    diff_payload = (latest_diff or {}).get("payload") if isinstance(latest_diff, dict) else {}
    coverage = (pack_payload or {}).get("coverage") if isinstance(pack_payload, dict) else {}
    assertions = (eval_payload or {}).get("assertions") if isinstance(eval_payload, dict) else {}
    issues = (eval_payload or {}).get("issues") if isinstance(eval_payload, dict) else None
    if not isinstance(issues, list): issues = []

    payload = {
        "schema_version": "0.1",
        "run": {"run_id": rid, "trace_id": trace_id, "status": run.get("status"),
                "task": run.get("task"), "start_time": run.get("start_time"), "end_time": run.get("end_time")},
        "links": {"evaluation_report_id": (latest_eval or {}).get("artifact_id") if isinstance(latest_eval, dict) else None,
                   "evidence_pack_id": (latest_pack or {}).get("artifact_id") if isinstance(latest_pack, dict) else None,
                   "evidence_diff_id": (latest_diff or {}).get("artifact_id") if isinstance(latest_diff, dict) else None},
        "evaluation": {"pass": (eval_payload or {}).get("pass") if isinstance(eval_payload, dict) else None,
                        "score": (eval_payload or {}).get("score") if isinstance(eval_payload, dict) else None,
                        "regression": (eval_payload or {}).get("regression") if isinstance(eval_payload, dict) else None,
                        "issues_count": len(issues), "issues_top": issues[:10]},
        "evidence": {"url": (pack_payload or {}).get("url") if isinstance(pack_payload, dict) else None,
                      "coverage": coverage, "diff_metrics": (diff_payload or {}).get("metrics"),
                      "diff_summary": (diff_payload or {}).get("summary")},
        "assertions": assertions, "syscalls": {"summary": syscall_summary,
            "sample": [{"id": (x or {}).get("id"), "kind": (x or {}).get("kind"), "name": (x or {}).get("name"),
                        "status": (x or {}).get("status"), "duration_ms": (x or {}).get("duration_ms"),
                        "error_code": (x or {}).get("error_code"), "error": (x or {}).get("error")}
                       for x in (syscall_items or [])[:50]]},
    }

    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind
    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.INVESTIGATE_REPORT, target_type="run", target_id=rid,
        version=f"investigate:{int(time.time())}", status="draft", payload=payload,
        metadata={"source": "auto_investigate"}, trace_id=str(trace_id) if trace_id else None, run_id=rid)
    return {"status": "ok", "artifact_id": art.artifact_id, "report": payload}


@router.get("/runs/{run_id}/state/latest", response_model=Dict[str, Any])
async def get_latest_run_state(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="run_state", limit=20, offset=0)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        from core.harness.restatement.run_state import default_run_state
        return {"status": "ok", "item": {"payload": default_run_state(run_id=rid, task=str(run.get("task") or "")), "artifact_id": None}}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.get("/runs/{run_id}/evidence_pack/latest", response_model=Dict[str, Any])
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


@router.post("/runs/{run_id}/evidence/diff", response_model=Dict[str, Any])
async def compute_run_evidence_diff(run_id: str, request: EvidenceDiffRequest, http_request: Request, rt: RuntimeDep = None):
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
    base_payload = dict(base_payload); new_payload = dict(new_payload)
    base_payload["evidence_pack_id"] = base_id; new_payload["evidence_pack_id"] = new_id
    from core.harness.evaluation.evidence_diff import compute_evidence_diff
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind
    diff = compute_evidence_diff(base_payload, new_payload)
    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.EVIDENCE_DIFF, target_type="run", target_id=rid,
        version=f"evidence_diff:{int(time.time())}", status="draft", payload=diff,
        metadata={"source": "manual", "base_evidence_pack_id": base_id, "new_evidence_pack_id": new_id},
        trace_id=run.get("trace_id"), run_id=rid)
    return {"status": "ok", "artifact_id": art.artifact_id, "diff": diff}


@router.post("/runs/{run_id}/state", response_model=Dict[str, Any])
async def upsert_run_state(run_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
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
        kind=LearningArtifactKind.RUN_STATE, target_type="run", target_id=rid,
        version=f"run_state:{int(time.time())}", status="draft", payload=norm,
        metadata={"source": "manual", "locked": bool(norm.get("locked"))},
        trace_id=run.get("trace_id"), run_id=rid)
    try:
        await store.append_run_event(run_id=rid, event_type="run_state", trace_id=run.get("trace_id"),
                                      tenant_id=actor.get("tenant_id"),
                                      payload={"artifact_id": art.artifact_id, "locked": bool(norm.get("locked")), "source": "manual"})
    except Exception:
            logging.getLogger("runs_eval").warning("best-effort skipped", exc_info=True)
    return {"status": "ok", "artifact_id": art.artifact_id, "state": norm}


@router.get("/runs/{run_id}/evidence", response_model=Dict[str, Any])
async def get_run_evidence(run_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    res = await store.list_learning_artifacts(target_type="run", target_id=rid, kind="evidence_pack", limit=5, offset=0)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    packs = []
    if isinstance(items, list):
        for item in items:
            payload = (item or {}).get("payload") if isinstance(item, dict) else None
            packs.append({"artifact_id": (item or {}).get("artifact_id") if isinstance(item, dict) else None,
                          "version": (item or {}).get("version") if isinstance(item, dict) else None, "payload": payload})
    return {"status": "ok", "run_id": rid, "evidence_packs": packs}


__all__ = ["router"]
