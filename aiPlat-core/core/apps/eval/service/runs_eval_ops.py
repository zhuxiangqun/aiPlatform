"""Run evaluation / investigate / evidence / state ops (platform thin via CoreFacade)."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

_log = logging.getLogger("aiplat.runs_eval_ops")


class RunsEvalGateFailed(Exception):
    """enforce_gate=True and report.pass is false — map to HTTP 409 in thin route."""

    def __init__(self, *, artifact_id: Any, report: Dict[str, Any]):
        self.artifact_id = artifact_id
        self.report = report
        super().__init__("evaluation_failed")


async def _require_store() -> Any:
    from core.api.core_facade import get_kernel_runtime

    rt = get_kernel_runtime()
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        raise RuntimeError("ExecutionStore not initialized")
    return store


def _latest(items: Any) -> Optional[Dict[str, Any]]:
    if isinstance(items, list) and items:
        return sorted(
            items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True
        )[0]
    return None


async def _require_run(store: Any, run_id: str) -> Dict[str, Any]:
    rid = str(run_id)
    run = await store.get_run_summary(run_id=rid)
    if not run:
        raise LookupError("run_not_found")
    return run


async def submit_run_evaluation(
    *,
    run_id: str,
    body: Dict[str, Any],
    actor: Dict[str, Any],
) -> Dict[str, Any]:
    from core.api.core_facade import (
        EvaluatorThresholds,
        apply_threshold_gate,
        persist_evaluation,
        validate_report,
        merge_from_evaluation,
        normalize_run_state,
        attach_eval_protocol,
        eval_protocol_from_run_evaluation,
    )
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)

    body = dict(body or {}) if isinstance(body, dict) else {}
    evaluator = str((body or {}).get("evaluator") or "evaluator").strip()
    report = (body or {}).get("report")
    thresholds0 = (
        (body or {}).get("thresholds")
        if isinstance((body or {}).get("thresholds"), dict)
        else {}
    )
    enforce_gate = bool((body or {}).get("enforce_gate", False))
    project_id = str((body or {}).get("project_id") or "").strip() or None
    url = str((body or {}).get("url") or "").strip() or None
    tag_template = str((body or {}).get("tag_template") or "").strip() or None
    base_evidence_pack_id_req = (
        str((body or {}).get("base_evidence_pack_id") or "").strip() or None
    )
    if not isinstance(report, dict):
        raise ValueError("missing_report")

    ok, reason = validate_report(report)
    if not ok:
        raise ValueError(f"invalid_report:{reason}")
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
        _log.warning(str(e), exc_info=True)

    saved = await persist_evaluation(
        execution_store=store,
        run_id=rid,
        trace_id=run.get("trace_id"),
        evaluator=evaluator,
        report=gated_report,
        thresholds=thresholds,
        actor=actor,
        metadata_extra={
            "project_id": project_id,
            "url": url,
            "tag_template": tag_template,
        },
    )
    try:
        mgr = LearningManager(execution_store=store)
        latest = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="run_state",
            limit=10,
            offset=0,
        )
        items = latest.get("items") if isinstance(latest, dict) else None
        cur: Dict[str, Any] = {}
        if isinstance(items, list) and items:
            items2 = sorted(
                items,
                key=lambda x: float((x or {}).get("created_at") or 0),
                reverse=True,
            )
            cur = (
                (items2[0] or {}).get("payload")
                if isinstance(items2[0], dict)
                else {}
            )
        cur2 = normalize_run_state(cur, run_id=rid)
        if not str(cur2.get("task") or "").strip():
            cur2["task"] = str(run.get("task") or "")
        merged = merge_from_evaluation(
            cur2, evaluation_report=gated_report, source="evaluator"
        )
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
    except Exception as e:
        _log.warning(str(e), exc_info=True)

    if enforce_gate and not bool(gated_report.get("pass")):
        raise RunsEvalGateFailed(
            artifact_id=saved.get("artifact_id"), report=gated_report
        )

    out = {
        "status": "ok",
        "artifact_id": saved.get("artifact_id"),
        "report": gated_report,
    }
    return attach_eval_protocol(
        out,
        eval_protocol_from_run_evaluation(
            run_id=rid,
            evaluator=evaluator,
            report=gated_report,
            artifact=saved,
        ),
    )


async def auto_evaluate_run(*, run_id: str) -> Dict[str, Any]:
    from core.api.core_facade import (
        attach_eval_protocol,
        eval_protocol_from_run_evaluation,
    )

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)

    latest_eval = None
    latest_pack = None
    try:
        r0 = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="evaluation_report",
            limit=10,
            offset=0,
        )
        latest_eval = _latest((r0 or {}).get("items"))
    except Exception as e:
        _log.warning(str(e), exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="evidence_pack",
            limit=10,
            offset=0,
        )
        latest_pack = _latest((r0 or {}).get("items"))
    except Exception as e:
        _log.warning(str(e), exc_info=True)

    syscall_summary: Dict[str, Any] = {"total": 0, "errors": 0}
    try:
        s0 = await store.list_syscall_events(run_id=rid, limit=200, offset=0)
        items = (s0 or {}).get("items") if isinstance(s0, dict) else []
        if isinstance(items, list):
            errs = [x for x in items if (x or {}).get("error")]
            syscall_summary = {"total": len(items), "errors": len(errs)}
    except Exception as e:
        _log.warning(str(e), exc_info=True)

    out = {
        "trace_id": run.get("trace_id"),
        "latest_eval": (
            (latest_eval or {}).get("payload", {})
            if isinstance(latest_eval, dict)
            else {}
        ),
        "latest_pack": (
            (latest_pack or {}).get("payload", {})
            if isinstance(latest_pack, dict)
            else {}
        ),
        "syscall_summary": syscall_summary,
    }
    return attach_eval_protocol(
        out,
        eval_protocol_from_run_evaluation(
            run_id=rid,
            artifact=latest_eval if isinstance(latest_eval, dict) else None,
            report=out["latest_eval"]
            if isinstance(out.get("latest_eval"), dict)
            else None,
        ),
    )


async def get_latest_run_evaluation(*, run_id: str) -> Dict[str, Any]:
    from core.api.core_facade import (
        attach_eval_protocol,
        eval_protocol_from_run_evaluation,
    )

    store = await _require_store()
    rid = str(run_id)
    await _require_run(store, rid)
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
    latest = _latest(items)
    out = {"status": "ok", "item": latest}
    return attach_eval_protocol(
        out,
        eval_protocol_from_run_evaluation(
            run_id=rid, artifact=latest if isinstance(latest, dict) else None
        ),
    )


async def get_latest_investigate_report(*, run_id: str) -> Dict[str, Any]:
    store = await _require_store()
    rid = str(run_id)
    res = await store.list_learning_artifacts(
        target_type="run",
        target_id=rid,
        kind="investigate_report",
        limit=20,
        offset=0,
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    return {"status": "ok", "item": _latest(items)}


async def auto_investigate_run(*, run_id: str) -> Dict[str, Any]:
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)
    trace_id = run.get("trace_id")

    latest_eval = None
    latest_pack = None
    latest_diff = None
    try:
        r0 = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="evaluation_report",
            limit=10,
            offset=0,
        )
        latest_eval = _latest((r0 or {}).get("items"))
    except Exception:
        _log.warning("best-effort skipped", exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="evidence_pack",
            limit=10,
            offset=0,
        )
        latest_pack = _latest((r0 or {}).get("items"))
    except Exception:
        _log.warning("best-effort skipped", exc_info=True)
    try:
        r0 = await store.list_learning_artifacts(
            target_type="run",
            target_id=rid,
            kind="evidence_diff",
            limit=10,
            offset=0,
        )
        latest_diff = _latest((r0 or {}).get("items"))
    except Exception:
        _log.warning("best-effort skipped", exc_info=True)

    syscall_items: list = []
    syscall_summary: Dict[str, Any] = {
        "total": 0,
        "errors": 0,
        "top_errors": [],
        "slow": [],
    }
    try:
        s0 = await store.list_syscall_events(run_id=rid, limit=200, offset=0)
        syscall_items = (s0 or {}).get("items") if isinstance(s0, dict) else []
        if not isinstance(syscall_items, list):
            syscall_items = []
        errs = [
            x
            for x in syscall_items
            if str((x or {}).get("status") or "").lower() not in {"ok", "success"}
            or (x or {}).get("error")
        ]
        counts: Dict[str, int] = {}
        for e in errs:
            code = str(
                (e or {}).get("error_code") or (e or {}).get("error") or "error"
            ).strip()
            counts[code] = counts.get(code, 0) + 1
        top_errors = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        slow = sorted(
            syscall_items,
            key=lambda x: float((x or {}).get("duration_ms") or 0),
            reverse=True,
        )[:10]
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
        _log.warning("best-effort skipped", exc_info=True)

    eval_payload = (
        (latest_eval or {}).get("payload") if isinstance(latest_eval, dict) else {}
    )
    pack_payload = (
        (latest_pack or {}).get("payload") if isinstance(latest_pack, dict) else {}
    )
    diff_payload = (
        (latest_diff or {}).get("payload") if isinstance(latest_diff, dict) else {}
    )
    coverage = (
        (pack_payload or {}).get("coverage") if isinstance(pack_payload, dict) else {}
    )
    assertions = (
        (eval_payload or {}).get("assertions") if isinstance(eval_payload, dict) else {}
    )
    issues = (
        (eval_payload or {}).get("issues") if isinstance(eval_payload, dict) else None
    )
    if not isinstance(issues, list):
        issues = []

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
            "evaluation_report_id": (latest_eval or {}).get("artifact_id")
            if isinstance(latest_eval, dict)
            else None,
            "evidence_pack_id": (latest_pack or {}).get("artifact_id")
            if isinstance(latest_pack, dict)
            else None,
            "evidence_diff_id": (latest_diff or {}).get("artifact_id")
            if isinstance(latest_diff, dict)
            else None,
        },
        "evaluation": {
            "pass": (eval_payload or {}).get("pass")
            if isinstance(eval_payload, dict)
            else None,
            "score": (eval_payload or {}).get("score")
            if isinstance(eval_payload, dict)
            else None,
            "regression": (eval_payload or {}).get("regression")
            if isinstance(eval_payload, dict)
            else None,
            "issues_count": len(issues),
            "issues_top": issues[:10],
        },
        "evidence": {
            "url": (pack_payload or {}).get("url")
            if isinstance(pack_payload, dict)
            else None,
            "coverage": coverage,
            "diff_metrics": (diff_payload or {}).get("metrics"),
            "diff_summary": (diff_payload or {}).get("summary"),
        },
        "assertions": assertions,
        "syscalls": {
            "summary": syscall_summary,
            "sample": [
                {
                    "id": (x or {}).get("id"),
                    "kind": (x or {}).get("kind"),
                    "name": (x or {}).get("name"),
                    "status": (x or {}).get("status"),
                    "duration_ms": (x or {}).get("duration_ms"),
                    "error_code": (x or {}).get("error_code"),
                    "error": (x or {}).get("error"),
                }
                for x in (syscall_items or [])[:50]
            ],
        },
    }

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


async def get_latest_run_state(*, run_id: str) -> Dict[str, Any]:
    from core.api.core_facade import default_run_state

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)
    res = await store.list_learning_artifacts(
        target_type="run", target_id=rid, kind="run_state", limit=20, offset=0
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {
            "status": "ok",
            "item": {
                "payload": default_run_state(
                    run_id=rid, task=str(run.get("task") or "")
                ),
                "artifact_id": None,
            },
        }
    return {"status": "ok", "item": _latest(items)}


async def get_latest_evidence_pack(*, run_id: str) -> Dict[str, Any]:
    store = await _require_store()
    rid = str(run_id)
    await _require_run(store, rid)
    res = await store.list_learning_artifacts(
        target_type="run", target_id=rid, kind="evidence_pack", limit=20, offset=0
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        return {"status": "ok", "item": None}
    return {"status": "ok", "item": _latest(items)}


async def compute_run_evidence_diff(
    *,
    run_id: str,
    base_evidence_pack_id: str,
    new_evidence_pack_id: str,
) -> Dict[str, Any]:
    from core.api.core_facade import compute_evidence_diff
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)
    base_id = str(base_evidence_pack_id or "").strip()
    new_id = str(new_evidence_pack_id or "").strip()
    if not base_id or not new_id:
        raise ValueError("missing_evidence_pack_ids")
    base_art = await store.get_learning_artifact(artifact_id=base_id)
    new_art = await store.get_learning_artifact(artifact_id=new_id)
    if not base_art or not new_art:
        raise LookupError("evidence_pack_not_found")
    base_payload = base_art.get("payload") if isinstance(base_art, dict) else None
    new_payload = new_art.get("payload") if isinstance(new_art, dict) else None
    if not isinstance(base_payload, dict) or not isinstance(new_payload, dict):
        raise ValueError("invalid_evidence_pack_payload")
    base_payload = dict(base_payload)
    new_payload = dict(new_payload)
    base_payload["evidence_pack_id"] = base_id
    new_payload["evidence_pack_id"] = new_id
    diff = compute_evidence_diff(base_payload, new_payload)
    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.EVIDENCE_DIFF,
        target_type="run",
        target_id=rid,
        version=f"evidence_diff:{int(time.time())}",
        status="draft",
        payload=diff,
        metadata={
            "source": "manual",
            "base_evidence_pack_id": base_id,
            "new_evidence_pack_id": new_id,
        },
        trace_id=run.get("trace_id"),
        run_id=rid,
    )
    return {"status": "ok", "artifact_id": art.artifact_id, "diff": diff}


async def upsert_run_state(
    *,
    run_id: str,
    state: Dict[str, Any],
    lock: Any,
    actor: Dict[str, Any],
) -> Dict[str, Any]:
    from core.api.core_facade import normalize_run_state
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    store = await _require_store()
    rid = str(run_id)
    run = await _require_run(store, rid)
    if not isinstance(state, dict):
        raise ValueError("missing_state")
    norm = normalize_run_state(state, run_id=rid)
    if lock is not None:
        norm["locked"] = bool(lock)
    norm["updated_by"] = {
        "source": "manual",
        "actor_id": actor.get("actor_id"),
        "actor_role": actor.get("actor_role"),
    }
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
            payload={
                "artifact_id": art.artifact_id,
                "locked": bool(norm.get("locked")),
                "source": "manual",
            },
        )
    except Exception:
        _log.warning("best-effort skipped", exc_info=True)
    return {"status": "ok", "artifact_id": art.artifact_id, "state": norm}


async def get_run_evidence(*, run_id: str) -> Dict[str, Any]:
    store = await _require_store()
    rid = str(run_id)
    await _require_run(store, rid)
    res = await store.list_learning_artifacts(
        target_type="run", target_id=rid, kind="evidence_pack", limit=5, offset=0
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    packs = []
    if isinstance(items, list):
        for item in items:
            payload = (item or {}).get("payload") if isinstance(item, dict) else None
            packs.append(
                {
                    "artifact_id": (item or {}).get("artifact_id")
                    if isinstance(item, dict)
                    else None,
                    "version": (item or {}).get("version")
                    if isinstance(item, dict)
                    else None,
                    "payload": payload,
                }
            )
    return {"status": "ok", "run_id": rid, "evidence_packs": packs}
