"""
Phase 6.x: Offline auto-rollback utilities.

These utilities are designed to be reusable by:
- scripts/learning_cli.py (offline CLI)
- core.server HTTP endpoints (management plane via HTTP)

Important:
- Operate only on ExecutionStore + learning_artifacts state transitions.
- Must remain side-effect free with respect to online runtime behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import time

from core.learning.manager import LearningManager
from core.learning.pipeline import artifact_from_regression_decision
from core.learning.release import require_rollback_approval, is_approved
from core.harness.infrastructure.approval.manager import ApprovalManager
from core.harness.infrastructure.approval.types import RequestStatus


def compute_exec_metrics(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(items)
    failures = 0
    duration_sum = 0.0
    duration_n = 0
    for r in items:
        st = (r.get("status") or "").lower()
        if st not in ("completed", "success", "succeeded"):
            failures += 1
        try:
            d = float(r.get("duration_ms") or 0.0)
            if d > 0:
                duration_sum += d
                duration_n += 1
        except Exception:
            pass
    return {
        "samples": n,
        "failures": failures,
        "error_rate": (failures / max(1, n)) if n else None,
        "avg_duration_ms": (duration_sum / duration_n) if duration_n else None,
    }


def merge_unique_cap(existing: Any, new: Any, *, cap: int) -> List[str]:
    """Merge two lists with stable order (existing first), dedupe, and cap length."""
    out: List[str] = []
    seen: set[str] = set()
    for src in (existing, new):
        if not isinstance(src, list):
            continue
        for x in src:
            if not isinstance(x, str) or not x:
                continue
            if x in seen:
                continue
            out.append(x)
            seen.add(x)
            if len(out) >= cap:
                return out
    return out


async def rollback_candidate(
    *,
    store,
    mgr: LearningManager,
    candidate_id: str,
    reason: str,
    now: float,
) -> bool:
    cand = await store.get_learning_artifact(candidate_id)
    if not cand or cand.get("kind") != "release_candidate":
        return False
    await mgr.set_artifact_status(
        artifact_id=candidate_id,
        status="rolled_back",
        metadata_update={"rolled_back_via": "auto-rollback-regression", "reason": reason, "rolled_back_at": now},
    )
    payload = cand.get("payload") if isinstance(cand.get("payload"), dict) else {}
    ids = payload.get("artifact_ids") if isinstance(payload.get("artifact_ids"), list) else []
    for aid in ids:
        if isinstance(aid, str) and aid:
            await mgr.set_artifact_status(
                artifact_id=aid,
                status="rolled_back",
                metadata_update={"rolled_back_by_candidate": candidate_id, "rolled_back_at": now},
            )
    return True


def _candidate_of(meta: Dict[str, Any]) -> Optional[str]:
    ar = meta.get("active_release") if isinstance(meta.get("active_release"), dict) else {}
    cid = ar.get("candidate_id")
    return str(cid) if isinstance(cid, str) and cid else None


async def _select_candidate_and_published_list(store, agent_id: str, candidate_id: Optional[str]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    la = await store.list_learning_artifacts(target_type="agent", target_id=agent_id, limit=50, offset=0)
    published = [x for x in (la.get("items") or []) if x.get("kind") == "release_candidate" and x.get("status") == "published"]
    published.sort(key=lambda x: float(x.get("created_at") or 0.0), reverse=True)
    if candidate_id:
        return candidate_id, published
    if not published:
        return None, published
    return str(published[0].get("artifact_id")), published


async def auto_rollback_regression(
    *,
    store,
    approval_manager: ApprovalManager,
    agent_id: str,
    candidate_id: Optional[str] = None,
    baseline_candidate_id: Optional[str] = None,
    current_window: int = 50,
    baseline_window: int = 50,
    min_samples: int = 10,
    error_rate_delta_threshold: float = 0.1,
    avg_duration_delta_threshold: Optional[float] = None,
    link_baseline: bool = False,
    max_linked_evidence: int = 200,
    require_approval: bool = False,
    approval_request_id: Optional[str] = None,
    user_id: str = "system",
    dry_run: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Phase 6.16-6.25: Offline auto rollback by regression detection + evidence linkage + approval gate.
    """
    now_ts = float(now) if now is not None else time.time()
    mgr = LearningManager(execution_store=store)

    candidate_id, published_candidates_sorted = await _select_candidate_and_published_list(store, agent_id, candidate_id)
    if not candidate_id:
        return {"status": "no_active_candidate"}

    current_window = int(current_window or 50)
    baseline_window = int(baseline_window or 50)
    min_samples = int(min_samples or 10)
    pull = max(500, (current_window + baseline_window) * 10)
    hist, _total = await store.list_agent_history(agent_id, limit=pull, offset=0)

    current: List[Dict[str, Any]] = []
    baseline: List[Dict[str, Any]] = []
    oldest_current_start: Optional[float] = None

    for r in hist:
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        cid = _candidate_of(meta)
        if cid == candidate_id:
            current.append(r)
            try:
                st = float(r.get("start_time") or 0.0)
                oldest_current_start = st if oldest_current_start is None else min(oldest_current_start, st)
            except Exception:
                pass
        if len(current) >= current_window:
            break

    if len(current) < min_samples:
        return {"status": "insufficient_current_samples", "candidate_id": candidate_id, "samples": len(current)}

    baseline_selection: Dict[str, Any] = {
        "mode": "explicit" if baseline_candidate_id else "auto",
        "chosen_candidate_id": None,
        "tried": [],
        "fallback": None,
    }

    if not baseline_candidate_id:
        # Prefer previous published candidates with multi-level fallback (Phase 6.18)
        for x in published_candidates_sorted:
            cid = str(x.get("artifact_id") or "")
            if cid and cid != candidate_id:
                baseline_selection["tried"].append({"candidate_id": cid, "samples": 0})

    def _collect_baseline_for_candidate(cid_filter: Optional[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in hist:
            try:
                st = float(r.get("start_time") or 0.0)
                if oldest_current_start is not None and st >= oldest_current_start:
                    continue
            except Exception:
                continue
            meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
            cid = _candidate_of(meta)
            if cid_filter is not None:
                if cid != cid_filter:
                    continue
            else:
                if cid == candidate_id:
                    continue
            out.append(r)
            if len(out) >= baseline_window:
                break
        return out

    if baseline_candidate_id:
        baseline = _collect_baseline_for_candidate(baseline_candidate_id)
        baseline_selection["chosen_candidate_id"] = baseline_candidate_id
        baseline_selection["tried"] = [{"candidate_id": baseline_candidate_id, "samples": len(baseline)}]
    else:
        chosen = None
        for item in baseline_selection["tried"]:
            cid_try = item.get("candidate_id")
            if not isinstance(cid_try, str) or not cid_try:
                continue
            b = _collect_baseline_for_candidate(cid_try)
            item["samples"] = len(b)
            if len(b) >= min_samples and chosen is None:
                chosen = cid_try
                baseline = b
                break
        if chosen is not None:
            baseline_candidate_id = chosen
            baseline_selection["chosen_candidate_id"] = chosen
            baseline_selection["mode"] = "prev_published"
        else:
            baseline = _collect_baseline_for_candidate(None)
            baseline_candidate_id = None
            baseline_selection["chosen_candidate_id"] = None
            baseline_selection["fallback"] = "not_equal_current"
            baseline_selection["mode"] = "not_equal_current"

    if len(baseline) < min_samples:
        return {
            "status": "insufficient_baseline_samples",
            "candidate_id": candidate_id,
            "baseline_candidate_id": baseline_candidate_id,
            "samples": len(baseline),
            "baseline_selection": baseline_selection,
        }

    cur_m = compute_exec_metrics(current)
    base_m = compute_exec_metrics(baseline)

    # Evidence links (Phase 6.20)
    current_execution_ids = [str(r.get("id")) for r in current if r.get("id")]
    baseline_execution_ids = [str(r.get("id")) for r in baseline if r.get("id")]
    evidence_trace_ids: List[str] = []
    for r in (current + baseline):
        tid = r.get("trace_id")
        if isinstance(tid, str) and tid and tid not in evidence_trace_ids:
            evidence_trace_ids.append(tid)
    evidence_trace_id = evidence_trace_ids[0] if evidence_trace_ids else None

    cur_er = float(cur_m["error_rate"] or 0.0)
    base_er = float(base_m["error_rate"] or 0.0)
    er_delta = cur_er - base_er

    cur_d = cur_m["avg_duration_ms"]
    base_d = base_m["avg_duration_ms"]
    d_delta = None
    try:
        if cur_d is not None and base_d is not None:
            d_delta = float(cur_d) - float(base_d)
    except Exception:
        d_delta = None

    should_rb = False
    reason_parts: List[str] = []
    if er_delta >= float(error_rate_delta_threshold):
        should_rb = True
        reason_parts.append(f"error_rate_delta={er_delta:.3f}>=thr({float(error_rate_delta_threshold):.3f})")
    if avg_duration_delta_threshold is not None and d_delta is not None and d_delta >= float(avg_duration_delta_threshold):
        should_rb = True
        reason_parts.append(f"avg_duration_delta_ms={d_delta:.1f}>=thr({float(avg_duration_delta_threshold):.1f})")

    out: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "agent_id": agent_id,
        "baseline_candidate_id": baseline_candidate_id,
        "baseline_selection": baseline_selection,
        "current": cur_m,
        "baseline": base_m,
        "error_rate_delta": er_delta,
        "avg_duration_delta_ms": d_delta,
        "should_rollback": should_rb,
    }

    if not should_rb or dry_run:
        out["rollback"] = "skipped"
        return out

    regression_report_id: Optional[str] = None
    report_run_id = f"auto-rollback-regression:{candidate_id}:{int(now_ts)}"

    # Phase 6.25 approval gate
    if require_approval:
        if approval_request_id:
            req = approval_manager.get_request(approval_request_id)
            if not req:
                return {"status": "not_found"}
            if not is_approved(approval_manager, approval_request_id):
                return {"status": "not_approved"}
            rid = (req.metadata or {}).get("regression_report_id") if getattr(req, "metadata", None) else None
            if isinstance(rid, str) and rid:
                regression_report_id = rid
        else:
            # Create report first, then request approval
            report = artifact_from_regression_decision(
                target_type="agent",
                target_id=agent_id,
                candidate_id=candidate_id,
                baseline_candidate_id=baseline_candidate_id,
                current=cur_m,
                baseline=base_m,
                deltas={
                    "error_rate_delta": er_delta,
                    "avg_duration_delta_ms": d_delta,
                    "evidence": {
                        "current_execution_ids": current_execution_ids,
                        "baseline_execution_ids": baseline_execution_ids,
                        "trace_ids": evidence_trace_ids,
                        "linked_current_execution_ids": [],
                        "linked_baseline_execution_ids": [],
                        "linked_evidence_cap": int(max_linked_evidence or 200),
                    },
                },
                decision={
                    "should_rollback": True,
                    "approval_required": True,
                    "reason": ";".join(reason_parts),
                    "thresholds": {
                        "error_rate_delta_threshold": float(error_rate_delta_threshold),
                        "avg_duration_delta_threshold": float(avg_duration_delta_threshold) if avg_duration_delta_threshold is not None else None,
                    },
                },
                baseline_selection=baseline_selection,
                artifact_version=f"regression:{candidate_id}:{int(now_ts)}",
                trace_id=evidence_trace_id,
                run_id=report_run_id,
                metadata={"source": "core_api", "mode": "auto-rollback-regression", "approval_gate": True},
            )
            await store.upsert_learning_artifact(report.to_record())
            regression_report_id = report.artifact_id

            req_id = await require_rollback_approval(
                approval_manager=approval_manager,
                user_id=user_id or "system",
                candidate_id=candidate_id,
                regression_report_id=regression_report_id,
                details="auto-rollback-regression",
            )
            return {
                "status": "approval_required",
                "candidate_id": candidate_id,
                "approval_request_id": req_id,
                "regression_report_id": regression_report_id,
            }

    # Phase 6.19: create regression_report if not already created
    if not regression_report_id:
        report = artifact_from_regression_decision(
            target_type="agent",
            target_id=agent_id,
            candidate_id=candidate_id,
            baseline_candidate_id=baseline_candidate_id,
            current=cur_m,
            baseline=base_m,
            deltas={
                "error_rate_delta": er_delta,
                "avg_duration_delta_ms": d_delta,
                "evidence": {
                    "current_execution_ids": current_execution_ids,
                    "baseline_execution_ids": baseline_execution_ids,
                    "trace_ids": evidence_trace_ids,
                    "linked_current_execution_ids": [],
                    "linked_baseline_execution_ids": [],
                },
            },
            decision={
                "should_rollback": True,
                "reason": ";".join(reason_parts),
                "thresholds": {
                    "error_rate_delta_threshold": float(error_rate_delta_threshold),
                    "avg_duration_delta_threshold": float(avg_duration_delta_threshold) if avg_duration_delta_threshold is not None else None,
                },
            },
            baseline_selection=baseline_selection,
            artifact_version=f"regression:{candidate_id}:{int(now_ts)}",
            trace_id=evidence_trace_id,
            run_id=report_run_id,
            metadata={"source": "core_api", "mode": "auto-rollback-regression"},
        )
        await store.upsert_learning_artifact(report.to_record())
        regression_report_id = report.artifact_id

    ok = await rollback_candidate(store=store, mgr=mgr, candidate_id=candidate_id, reason=";".join(reason_parts), now=now_ts)
    out["rollback"] = "done" if ok else "failed"
    out["regression_report_id"] = regression_report_id
    out["regression_report_run_id"] = report_run_id
    out["regression_report_trace_id"] = evidence_trace_id
    if require_approval and approval_request_id:
        out["approval_request_id"] = approval_request_id

    # Phase 6.21: link current executions (idempotent)
    linked_current: List[str] = []
    for r in current:
        eid = r.get("id")
        if not isinstance(eid, str) or not eid:
            continue
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        if meta.get("regression_report_id") == regression_report_id:
            continue
        meta2 = dict(meta)
        meta2.update(
            {
                "regression_report_id": regression_report_id,
                "regression_report_run_id": report_run_id,
                "regression_report_trace_id": evidence_trace_id,
                "regression_report_kind": "auto-rollback-regression",
            }
        )
        await store.upsert_agent_execution(
            {
                "id": eid,
                "agent_id": r.get("agent_id") or agent_id,
                "status": r.get("status"),
                "input": r.get("input") or {},
                "output": r.get("output") or {},
                "error": r.get("error"),
                "start_time": r.get("start_time"),
                "end_time": r.get("end_time"),
                "duration_ms": r.get("duration_ms"),
                "trace_id": r.get("trace_id"),
                "metadata": meta2,
                "approval_request_id": r.get("approval_request_id"),
            }
        )
        linked_current.append(eid)

    out["linked_current_executions"] = len(linked_current)
    out["linked_current_execution_ids"] = linked_current

    linked_baseline: List[str] = []
    if link_baseline:
        for r in baseline:
            eid = r.get("id")
            if not isinstance(eid, str) or not eid:
                continue
            meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
            if meta.get("regression_report_id") == regression_report_id:
                continue
            meta2 = dict(meta)
            meta2.update(
                {
                    "regression_report_id": regression_report_id,
                    "regression_report_run_id": report_run_id,
                    "regression_report_trace_id": evidence_trace_id,
                    "regression_report_kind": "auto-rollback-regression",
                }
            )
            await store.upsert_agent_execution(
                {
                    "id": eid,
                    "agent_id": r.get("agent_id") or agent_id,
                    "status": r.get("status"),
                    "input": r.get("input") or {},
                    "output": r.get("output") or {},
                    "error": r.get("error"),
                    "start_time": r.get("start_time"),
                    "end_time": r.get("end_time"),
                    "duration_ms": r.get("duration_ms"),
                    "trace_id": r.get("trace_id"),
                    "metadata": meta2,
                    "approval_request_id": r.get("approval_request_id"),
                }
            )
            linked_baseline.append(eid)
        out["linked_baseline_executions"] = len(linked_baseline)
        out["linked_baseline_execution_ids"] = linked_baseline

    # Update regression_report evidence (Phase 6.22-6.24)
    cap = max(1, int(max_linked_evidence or 200))
    rep = await store.get_learning_artifact(regression_report_id)
    if rep:
        payload = rep.get("payload") if isinstance(rep.get("payload"), dict) else {}
        deltas = payload.get("deltas") if isinstance(payload.get("deltas"), dict) else {}
        ev = deltas.get("evidence") if isinstance(deltas.get("evidence"), dict) else {}
        merged_current = merge_unique_cap(ev.get("linked_current_execution_ids"), linked_current, cap=cap)
        merged_baseline = merge_unique_cap(ev.get("linked_baseline_execution_ids"), linked_baseline, cap=cap)
        ev["linked_current_execution_ids"] = merged_current
        ev["linked_baseline_execution_ids"] = merged_baseline
        ev["linked_evidence_cap"] = cap
        ev["linked_current_truncated"] = len(linked_current) > len(merged_current)
        ev["linked_baseline_truncated"] = len(linked_baseline) > len(merged_baseline)
        deltas["evidence"] = ev
        payload["deltas"] = deltas
        await store.upsert_learning_artifact(
            {
                "artifact_id": rep.get("artifact_id"),
                "kind": rep.get("kind"),
                "target_type": rep.get("target_type"),
                "target_id": rep.get("target_id"),
                "version": rep.get("version"),
                "status": rep.get("status"),
                "trace_id": rep.get("trace_id"),
                "run_id": rep.get("run_id"),
                "payload": payload,
                "metadata": rep.get("metadata") or {},
                "created_at": rep.get("created_at"),
            }
        )
        out["linked_evidence_cap"] = cap
        out["linked_current_truncated"] = ev["linked_current_truncated"]
        out["linked_baseline_truncated"] = ev["linked_baseline_truncated"]

    # Link from candidate metadata (best effort, Phase 6.19)
    try:
        await mgr.set_artifact_status(
            artifact_id=candidate_id,
            status="rolled_back",
            metadata_update={"rollback_regression_report_id": regression_report_id},
        )
    except Exception:
        pass

    return out


async def cleanup_rollback_approvals(
    *,
    store,
    approval_manager: ApprovalManager,
    now: Optional[float] = None,
    dry_run: bool = False,
    user_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    page_size: int = 500,
) -> Dict[str, Any]:
    """
    Phase 6.26-6.27: Cancel stale pending rollback approvals.

    Important: do NOT mutate while paginating with offset; use two-phase (collect then cancel).
    """
    now_ts = float(now) if now is not None else time.time()
    page_size = max(1, min(int(page_size or 500), 2000))

    checked = 0
    to_process: List[Dict[str, str]] = []
    offset = 0
    while True:
        page = await store.list_approval_requests(
            status=RequestStatus.PENDING.value,
            user_id=user_id,
            limit=page_size,
            offset=offset,
        )
        items = page.get("items") or []
        if not items:
            break
        checked += len(items)
        for it in items:
            if it.get("operation") != "learning:rollback_release":
                continue
            meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            cid = meta.get("candidate_id")
            rid = it.get("request_id")
            if not isinstance(cid, str) or not cid:
                continue
            if not isinstance(rid, str) or not rid:
                continue
            if candidate_id and cid != candidate_id:
                continue
            to_process.append({"request_id": rid, "candidate_id": cid})
        if len(items) < page_size:
            break
        offset += page_size

    cancelled: List[Dict[str, Any]] = []
    kept = 0
    for it in to_process:
        cid = it["candidate_id"]
        rid = it["request_id"]
        cand = await store.get_learning_artifact(cid)
        reason = None
        if not cand:
            reason = "candidate_not_found"
        else:
            st = cand.get("status")
            if st != "published":
                reason = f"candidate_status={st}"
        if reason is None:
            kept += 1
            continue
        if dry_run:
            cancelled.append({"approval_request_id": rid, "candidate_id": cid, "reason": reason})
            continue
        req = approval_manager.get_request(rid)
        if not req:
            continue
        await approval_manager.cancel_request(req.request_id)
        cancelled.append({"approval_request_id": req.request_id, "candidate_id": cid, "reason": reason})

    return {"now": now_ts, "checked": checked, "matched": len(to_process), "kept": kept, "cancelled": cancelled}

