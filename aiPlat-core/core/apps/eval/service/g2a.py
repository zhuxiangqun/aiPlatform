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
    """汇总 G2a 锁金状态（任务数 / 已裁决 / v0_locked）；永不宣称 accuracy。

    Args:
        tenant_id: 评测租户。
        db_path: 可选 EvalStore 路径；空则默认。

    Returns:
        含 ``v0_lock_ready`` / ``g2a_ready`` / ``accuracy_claim=False`` 的状态 dict。
    """
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
    """列出尚未裁决的人工复核队列条目。

    Args:
        tenant_id: 评测租户。
        annotator: 标注者标识。
        limit: 最多返回条数。
        db_path: 可选 EvalStore 路径。

    Returns:
        含 ``pending`` 列表与 ``total`` 的 dict。
    """
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
    """仅 AI 预标注：用确定性 judge 建议 pass；不裁决、不锁金。

    Args:
        tenant_id: 评测租户。
        annotator: 标注者标识。
        limit: 待处理标签上限。
        db_path: 可选 EvalStore 路径。

    Returns:
        含 ``updated``；``adjudicated`` 恒为 False。
    """
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
    """单人裁决一条标签（D5；κ 不适用）。

    Args:
        label_id: 标签 ID。
        passed: 人工判定是否通过。
        notes: 可选备注。
        rationale: 裁决理由；空则写默认 D5 说明。
        tenant_id: 评测租户。
        db_path: 可选 EvalStore 路径。

    Returns:
        含更新后 ``label``；``kappa`` 恒为 None。
    """
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
    """在 ≥30 任务且 ≥30 单人裁决后锁定 gold v0；只写 store meta，不宣称 accuracy。

    Args:
        tenant_id: 评测租户。
        force: 诚实锁禁止：未就绪时 force 仍失败。
        db_path: 可选 EvalStore 路径。

    Returns:
        成功时 ``v0_locked=True``；未就绪或非法 force 返回 error。
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
    """v0 锁定后跑本地门禁；可设 ``gate_claim``，永不设 ``accuracy_claim``。

    Args:
        mode: 门禁模式（如 nightly）。
        tenant_id: 评测租户。
        set_id: 金标集；空则取状态中的 set_id。
        limit: 可选任务上限。
        db_path: 可选 EvalStore 路径。

    Returns:
        E5 门禁结果并附 ``g2a`` 状态；``accuracy_claim`` 恒 False。
    """
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
