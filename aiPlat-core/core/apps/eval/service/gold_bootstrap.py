"""EVAL_V1 E3 — bootstrap gold set (≥15 runnable) + single-reviewer label queue.

Does not lock v0 (needs 30 + human adjudication). Does not compute κ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.eval.service.store import (
    STORE_SCHEMA_VERSION,
    get_eval_store,
    import_code_review_gold,
)

E3_MIN_RUNNABLE = 15
E3_V0_LOCK_TARGET = 30
E3_ANNOTATOR = "solo_reviewer"  # D5: single human reviewer


def _workspace_gold_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )


def bootstrap_e3_gold(
    *,
    tenant_id: str = "eval-v1",
    gold_dir: Optional[str] = None,
    annotator: str = E3_ANNOTATOR,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Import code-review-gold → EvalStore and open a solo review label per task.

    Idempotent: re-import replaces tasks; labels are created only when missing
    for (task_id, annotator).
    """
    root = Path(gold_dir).expanduser() if gold_dir else _workspace_gold_dir()
    imported = import_code_review_gold(
        gold_dir=str(root),
        tenant_id=tenant_id,
        set_name="eval-v1-gold-v0",
        set_version="e3-bootstrap",
        db_path=db_path,
    )
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    set_id = imported["set_id"]
    tasks = store.list_tasks(set_id=set_id, limit=5000)
    labels_created = 0
    for t in tasks:
        # Skip if annotator already has a label on this task
        existing = _labels_for_task(store, t["id"], annotator)
        if existing:
            continue
        store.create_label(
            task_id=t["id"],
            annotator=annotator,
            label={
                "status": "pending_review",
                "pass": None,
                "notes": "",
                "protocol": "eval.v0.solo_review",
            },
            rationale="E3 queue — awaiting solo human review (D5; no κ)",
            adjudicated=False,
        )
        labels_created += 1

    runnable = len(tasks)
    return {
        "ok": True,
        "schema_version": STORE_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "set_id": set_id,
        "gold_dir": str(root),
        "imported": imported.get("imported", 0),
        "task_count": runnable,
        "labels_created": labels_created,
        "e3_min_runnable": E3_MIN_RUNNABLE,
        "e3_v0_lock_target": E3_V0_LOCK_TARGET,
        "runnable_gate": runnable >= E3_MIN_RUNNABLE,
        "v0_locked": False,  # requires 30 + human adjudication
        "annotator": annotator,
        "store": store.health(),
        "source_slice": "code_review_gold",
    }


def _labels_for_task(store, task_id: str, annotator: str) -> List[Dict[str, Any]]:
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT id FROM eval_labels WHERE task_id=? AND annotator=?",
            (task_id, annotator),
        ).fetchall()
    return [{"id": r["id"]} for r in rows]


def e3_status(*, tenant_id: str = "eval-v1", db_path: Optional[str] = None) -> Dict[str, Any]:
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    sets = [s for s in store.list_sets(limit=50) if "gold" in (s.get("name") or "").lower() or "crg" in (s.get("id") or "")]
    # Prefer set_crg_* from import
    set_id = None
    for s in store.list_sets(limit=100):
        if str(s.get("id", "")).startswith("set_crg_"):
            set_id = s["id"]
            break
    if not set_id and sets:
        set_id = sets[0]["id"]
    tasks = store.list_tasks(set_id=set_id or "", limit=5000) if set_id else []
    pending = 0
    adjudicated = 0
    with store._connect() as conn:
        if set_id:
            pending = int(
                conn.execute(
                    "SELECT COUNT(*) FROM eval_labels l "
                    "JOIN eval_tasks t ON t.id=l.task_id "
                    "WHERE t.set_id=? AND l.adjudicated=0",
                    (set_id,),
                ).fetchone()[0]
            )
            adjudicated = int(
                conn.execute(
                    "SELECT COUNT(*) FROM eval_labels l "
                    "JOIN eval_tasks t ON t.id=l.task_id "
                    "WHERE t.set_id=? AND l.adjudicated=1",
                    (set_id,),
                ).fetchone()[0]
            )
    n = len(tasks)
    return {
        "ok": True,
        "set_id": set_id,
        "task_count": n,
        "labels_pending": pending,
        "labels_adjudicated": adjudicated,
        "runnable_gate": n >= E3_MIN_RUNNABLE,
        "v0_lock_ready": n >= E3_V0_LOCK_TARGET and adjudicated >= E3_V0_LOCK_TARGET,
        "v0_locked": False,
        "kappa": None,  # D5: not computed on solo review
        "e3_min_runnable": E3_MIN_RUNNABLE,
        "e3_v0_lock_target": E3_V0_LOCK_TARGET,
        "store": store.health(),
    }
