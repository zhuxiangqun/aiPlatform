"""EVAL_V1 G2c — single-annotator self-consistency (intra-rater), not accuracy.

Honesty:
- Never sets accuracy_claim.
- κ is intra_rater_kappa only — never call it inter-annotator.
- Does not open G2b.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.apps.eval.service.g2a import g2a_status
from core.apps.eval.service.gold_bootstrap import E3_ANNOTATOR
from core.apps.eval.service.store import get_eval_store

G2C_RETEST_ANNOTATOR = "g2c_retest"
META_G2C_REPORT = "g2c_report_json"
SCHEMA = "eval.g2c.v0"


def _pass_of(label_row: Dict[str, Any]) -> Optional[bool]:
    lab = label_row.get("label") or {}
    if "pass" in lab:
        return bool(lab["pass"])
    if "passed" in lab:
        return bool(lab["passed"])
    return None


def cohen_kappa_binary(pairs: List[Tuple[bool, bool]]) -> Dict[str, Any]:
    """Cohen's κ for binary (pass/fail) paired ratings. Empty → null κ."""
    n = len(pairs)
    if n == 0:
        return {
            "n": 0,
            "agreement": None,
            "intra_rater_kappa": None,
            "confusion": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
        }
    tp = tn = fp = fn = 0
    for a, b in pairs:
        if a and b:
            tp += 1
        elif (not a) and (not b):
            tn += 1
        elif (not a) and b:
            fp += 1
        else:
            fn += 1
    agree = (tp + tn) / n
    # marginals
    p1 = (tp + fn) / n  # rater1 pass rate
    p2 = (tp + fp) / n  # rater2 pass rate
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    if abs(1.0 - pe) < 1e-12:
        kappa = 1.0 if agree == 1.0 else 0.0
    else:
        kappa = (agree - pe) / (1.0 - pe)
    return {
        "n": n,
        "agreement": round(agree, 4),
        "intra_rater_kappa": round(kappa, 4),
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "chance_agreement": round(pe, 4),
    }


def g2c_status(*, tenant_id: str = "eval-v1", db_path: Optional[str] = None) -> Dict[str, Any]:
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    g2a = g2a_status(tenant_id=tenant_id, db_path=db_path)
    set_id = str(g2a.get("set_id") or "")
    primary = store.list_labels(
        set_id=set_id, annotator=E3_ANNOTATOR, adjudicated=True, limit=5000
    )
    retest = store.list_labels(
        set_id=set_id, annotator=G2C_RETEST_ANNOTATOR, adjudicated=False, limit=5000
    )
    # also count adjudicated retests
    retest_adj = store.list_labels(
        set_id=set_id, annotator=G2C_RETEST_ANNOTATOR, adjudicated=True, limit=5000
    )
    retest_all = {r["task_id"]: r for r in [*retest, *retest_adj]}
    paired = 0
    for lab in primary:
        if lab["task_id"] in retest_all and _pass_of(lab) is not None and _pass_of(
            retest_all[lab["task_id"]]
        ) is not None:
            paired += 1
    return {
        "ok": True,
        "schema_version": SCHEMA,
        "tenant_id": tenant_id,
        "set_id": set_id,
        "claim_kind": "self_consistency",
        "accuracy_claim": False,
        "kappa_kind": "intra_rater",
        "v0_locked": bool(g2a.get("v0_locked")),
        "primary_adjudicated": len(primary),
        "retest_count": len(retest_all),
        "paired_count": paired,
        "g2c_ready": bool(g2a.get("v0_locked")) and paired >= 1,
        "note": (
            "G2c = single-annotator test-retest (self-consistency). "
            "Not accuracy; not inter-annotator κ; G2b remains deferred."
        ),
        "g2a": {
            "v0_locked": g2a.get("v0_locked"),
            "labels_adjudicated": g2a.get("labels_adjudicated"),
            "accuracy_claim": False,
        },
    }


def list_g2c_retest_queue(
    *,
    tenant_id: str = "eval-v1",
    limit: int = 100,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Adjudicated primary labels that still lack a g2c_retest label."""
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = g2c_status(tenant_id=tenant_id, db_path=db_path)
    set_id = str(st.get("set_id") or "")
    primary = store.list_labels(
        set_id=set_id, annotator=E3_ANNOTATOR, adjudicated=True, limit=5000
    )
    retest = {
        r["task_id"]
        for r in store.list_labels(
            set_id=set_id, annotator=G2C_RETEST_ANNOTATOR, limit=5000
        )
    }
    pending = []
    for lab in primary:
        if lab["task_id"] in retest:
            continue
        pending.append(
            {
                "task_id": lab["task_id"],
                "primary_label_id": lab["id"],
                "primary_pass": _pass_of(lab),
            }
        )
        if len(pending) >= int(limit):
            break
    return {
        "ok": True,
        "set_id": set_id,
        "annotator": G2C_RETEST_ANNOTATOR,
        "pending": pending,
        "total": len(pending),
        "accuracy_claim": False,
        "claim_kind": "self_consistency",
    }


def record_g2c_retest(
    task_id: str,
    *,
    passed: bool,
    notes: str = "",
    rationale: str = "",
    tenant_id: str = "eval-v1",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Record same-annotator blind retest (does not adjudicate; not a second annotator)."""
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    existing = store.list_labels(annotator=G2C_RETEST_ANNOTATOR, limit=5000)
    for row in existing:
        if row["task_id"] == task_id:
            updated = store.update_label_payload(
                row["id"],
                label={
                    **(row.get("label") or {}),
                    "pass": bool(passed),
                    "status": "g2c_retest",
                    "protocol": "eval.v0.g2c_self_consistency",
                    "notes": notes,
                },
                rationale=rationale
                or "G2c same-annotator retest (intra-rater; not second annotator)",
                adjudicated=False,
            )
            return {
                "ok": True,
                "label": updated,
                "accuracy_claim": False,
                "claim_kind": "self_consistency",
                "updated": True,
            }
    created = store.create_label(
        task_id=task_id,
        annotator=G2C_RETEST_ANNOTATOR,
        label={
            "pass": bool(passed),
            "status": "g2c_retest",
            "protocol": "eval.v0.g2c_self_consistency",
            "notes": notes,
        },
        rationale=rationale
        or "G2c same-annotator retest (intra-rater; not second annotator)",
        adjudicated=False,
    )
    return {
        "ok": True,
        "label": created,
        "accuracy_claim": False,
        "claim_kind": "self_consistency",
        "updated": False,
    }


def compute_g2c_report(
    *,
    tenant_id: str = "eval-v1",
    db_path: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Pair primary adjudicated vs g2c_retest → intra-rater agreement/κ."""
    import json

    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    st = g2c_status(tenant_id=tenant_id, db_path=db_path)
    set_id = str(st.get("set_id") or "")
    primary = {
        lab["task_id"]: lab
        for lab in store.list_labels(
            set_id=set_id, annotator=E3_ANNOTATOR, adjudicated=True, limit=5000
        )
    }
    retest = {
        lab["task_id"]: lab
        for lab in store.list_labels(
            set_id=set_id, annotator=G2C_RETEST_ANNOTATOR, limit=5000
        )
    }
    pairs: List[Tuple[bool, bool]] = []
    paired_tasks: List[str] = []
    for tid, p in primary.items():
        r = retest.get(tid)
        if not r:
            continue
        pa, rb = _pass_of(p), _pass_of(r)
        if pa is None or rb is None:
            continue
        pairs.append((pa, rb))
        paired_tasks.append(tid)
    stats = cohen_kappa_binary(pairs)
    out: Dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA,
        "tenant_id": tenant_id,
        "set_id": set_id,
        "claim_kind": "self_consistency",
        "accuracy_claim": False,
        "kappa_kind": "intra_rater",
        "intra_rater_kappa": stats["intra_rater_kappa"],
        "agreement": stats["agreement"],
        "n_paired": stats["n"],
        "confusion": stats["confusion"],
        "chance_agreement": stats.get("chance_agreement"),
        "paired_task_ids": paired_tasks[:50],
        "note": (
            "Self-consistency (intra-rater) only. "
            "Not accuracy; not inter-annotator κ; G2b deferred."
        ),
    }
    if persist:
        store.set_meta(META_G2C_REPORT, json.dumps(out, ensure_ascii=False))
    return out
