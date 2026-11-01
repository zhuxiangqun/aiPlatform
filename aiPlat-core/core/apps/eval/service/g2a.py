"""EVAL_V1 G2a — lock v0 gold (30 + solo adjudication) + local gate claim.

Honesty: engineering calibration only. Never sets accuracy_claim.
κ remains null under D5 solo review.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.apps.eval.service.gate_v1 import run_e5_gate
from core.apps.eval.service.gold_bootstrap import (
    E3_ANNOTATOR,
    E3_V0_LOCK_TARGET,
    e3_status,
)
from core.apps.eval.service.judge_v1 import score_task_match_only
from core.apps.eval.service.store import get_eval_store

META_V0_LOCKED = "v0_locked"
META_V0_LOCKED_AT = "v0_locked_at"
META_G2A_REPORT = "g2a_report_id"


def _is_v0_locked(store) -> bool:
    return (store.get_meta(META_V0_LOCKED) or "").strip().lower() in {"1", "true", "yes"}


def g2a_status(*, tenant_id: str = "eval-v1", db_path: Optional[str] = None) -> Dict[str, Any]:
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = e3_status(tenant_id=tenant_id, db_path=db_path)
    locked = _is_v0_locked(store)
    # Refresh lock_ready from live counts
    lock_ready = (
        int(st.get("task_count") or 0) >= E3_V0_LOCK_TARGET
        and int(st.get("labels_adjudicated") or 0) >= E3_V0_LOCK_TARGET
    )
    return {
        "ok": True,
        "schema_version": "eval.g2a.v0",
        "tenant_id": tenant_id,
        "set_id": st.get("set_id"),
        "task_count": st.get("task_count"),
        "labels_pending": st.get("labels_pending"),
        "labels_adjudicated": st.get("labels_adjudicated"),
        "v0_lock_target": E3_V0_LOCK_TARGET,
        "v0_lock_ready": lock_ready,
        "v0_locked": locked,
        "g2a_ready": locked and lock_ready,
        "accuracy_claim": False,
        "kappa": None,
        "note": (
            "G2a = engineering calibration (local gate / UI preview). "
            "Not accuracy; κ N/A under D5 solo review."
        ),
        "e3": st,
    }


def list_review_queue(
    *,
    tenant_id: str = "eval-v1",
    annotator: str = E3_ANNOTATOR,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = e3_status(tenant_id=tenant_id, db_path=db_path)
    set_id = str(st.get("set_id") or "")
    pending = store.list_labels(
        set_id=set_id, annotator=annotator, adjudicated=False, limit=limit
    )
    return {
        "ok": True,
        "set_id": set_id,
        "annotator": annotator,
        "pending": pending,
        "total": len(pending),
    }


def preannotate_review_queue(
    *,
    tenant_id: str = "eval-v1",
    annotator: str = E3_ANNOTATOR,
    limit: int = 500,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """AI pre-annotation only: suggest pass from deterministic judge; does NOT adjudicate."""
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = e3_status(tenant_id=tenant_id, db_path=db_path)
    set_id = str(st.get("set_id") or "")
    if not set_id:
        raise ValueError("no gold set; run bootstrap_e3_gold first")
    tasks = {t["id"]: t for t in store.list_tasks(set_id=set_id, limit=5000)}
    pending = store.list_labels(
        set_id=set_id, annotator=annotator, adjudicated=False, limit=limit
    )
    updated = 0
    for lab in pending:
        task = tasks.get(lab["task_id"])
        if not task:
            continue
        scored = score_task_match_only(task)
        label = dict(lab.get("label") or {})
        label["status"] = "pending_review"
        label["ai_preannotate"] = {
            "pass": bool(scored.get("pass")),
            "score": scored.get("score"),
            "reason": scored.get("reason"),
            "protocol": "eval.v0.ai_preannotate",
        }
        store.update_label_payload(
            lab["id"],
            label=label,
            rationale=(
                lab.get("rationale")
                or "E3 queue — AI preannotate only; awaiting solo human adjudication (D5)"
            ),
            adjudicated=False,
        )
        updated += 1
    return {
        "ok": True,
        "set_id": set_id,
        "updated": updated,
        "adjudicated": False,
        "note": "AI pre-annotation only; human must adjudicate before lock_v0",
    }


def adjudicate_label(
    label_id: str,
    *,
    passed: bool,
    notes: str = "",
    rationale: str = "",
    tenant_id: str = "eval-v1",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    row = store.adjudicate_label(
        label_id,
        passed=passed,
        notes=notes,
        rationale=rationale or "solo human adjudication (D5; no κ)",
        label_extra={"protocol": "eval.v0.solo_adjudication"},
    )
    return {"ok": True, "label": row, "kappa": None}


def lock_v0(
    *,
    tenant_id: str = "eval-v1",
    force: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Lock gold v0 when ≥30 tasks and ≥30 solo-adjudicated labels.

    Does not claim accuracy. Sets store meta only.
    """
    from datetime import datetime, timezone

    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = e3_status(tenant_id=tenant_id, db_path=db_path)
    n = int(st.get("task_count") or 0)
    adj = int(st.get("labels_adjudicated") or 0)
    ready = n >= E3_V0_LOCK_TARGET and adj >= E3_V0_LOCK_TARGET
    if not ready and not force:
        return {
            "ok": False,
            "error": "v0_lock_not_ready",
            "task_count": n,
            "labels_adjudicated": adj,
            "v0_lock_target": E3_V0_LOCK_TARGET,
            "accuracy_claim": False,
        }
    if force and not ready:
        return {
            "ok": False,
            "error": "force_disabled_honesty",
            "note": "force lock without 30 adjudicated is forbidden (G2a honesty)",
            "accuracy_claim": False,
        }
    now = datetime.now(timezone.utc).isoformat()
    store.set_meta(META_V0_LOCKED, "true")
    store.set_meta(META_V0_LOCKED_AT, now)
    return {
        "ok": True,
        "v0_locked": True,
        "locked_at": now,
        "task_count": n,
        "labels_adjudicated": adj,
        "accuracy_claim": False,
        "kappa": None,
        "note": "v0 locked for G2a engineering calibration; not accuracy claim",
    }


def run_g2a_gate(
    *,
    mode: str = "nightly",
    tenant_id: str = "eval-v1",
    set_id: str = "",
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run local gate after v0 lock; may set gate_claim=true, never accuracy_claim."""
    status = g2a_status(tenant_id=tenant_id, db_path=db_path)
    if not status.get("v0_locked"):
        return {
            "ok": False,
            "error": "v0_not_locked",
            "g2a": status,
            "gate_claim": False,
            "accuracy_claim": False,
            "note": "lock_v0 first (≥30 tasks + ≥30 solo adjudicated)",
        }
    out = run_e5_gate(
        mode=mode,
        tenant_id=tenant_id,
        set_id=set_id or str(status.get("set_id") or ""),
        candidate=f"g2a:{mode}",
        limit=limit,
        db_path=db_path,
    )
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    if out.get("gate_claim") and out.get("report_id"):
        store.set_meta(META_G2A_REPORT, str(out["report_id"]))
        out["note"] = (
            "G2a local gate claim (engineering calibration). "
            "accuracy_claim=false; κ=null (D5)."
        )
    elif not out.get("engineering_pass"):
        out["note"] = "G2a gate ran but engineering thresholds failed; no gate claim"
    out["accuracy_claim"] = False
    out["g2a"] = status
    out["kappa"] = None
    return out
