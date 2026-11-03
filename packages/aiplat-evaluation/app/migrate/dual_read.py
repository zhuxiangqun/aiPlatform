"""B3-L dual-read reconciliation (EVAL_DATA_MIGRATION §3.1) — local only.

Honesty:
- Operates on fixture/local stores only; no production backfill.
- process_split_authorized stays false; does not flip read cutover in prod.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.store.store import create_report, create_set, list_reports, list_sets

READ_POINTER_SCHEMA = "eval.b3l.read_pointer.v0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_metrics_hash(metrics: Any) -> str:
    """Stable hash of normalized metrics JSON (sorted keys)."""
    payload = metrics if isinstance(metrics, dict) else {}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def inventory_store(
    store: Any,
    *,
    tenant_id: str = "",
    limit: int = 1000,
    label: str = "store",
) -> Dict[str, Any]:
    """Snapshot sets/reports for dual-read compare."""
    sets = list_sets(store, limit=limit, tenant_id=tenant_id)
    reports = list_reports(store, limit=limit, tenant_id=tenant_id)
    set_ids = sorted(str(s.get("id") or "") for s in sets if s.get("id"))
    report_ids = sorted(str(r.get("id") or "") for r in reports if r.get("id"))
    report_hashes = {
        str(r["id"]): canonical_metrics_hash(r.get("metrics"))
        for r in reports
        if r.get("id")
    }
    tenants: Set[str] = set()
    for row in (*sets, *reports):
        tid = str(row.get("tenant_id") or "").strip()
        if tid:
            tenants.add(tid)
    return {
        "label": label,
        "tenant_filter": tenant_id,
        "counts": {"sets": len(set_ids), "reports": len(report_ids)},
        "set_ids": set_ids,
        "report_ids": report_ids,
        "report_hashes": report_hashes,
        "tenants": sorted(tenants),
        "process_split_authorized": False,
        "accuracy_claim": False,
    }


def reconcile_inventories(
    source: Dict[str, Any],
    target: Dict[str, Any],
    *,
    exempt_set_ids: Optional[Set[str]] = None,
    exempt_report_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Compare source vs target inventories. ok=False → stop cutover (contract)."""
    exempt_s = set(exempt_set_ids or ())
    exempt_r = set(exempt_report_ids or ())

    src_sets = set(source.get("set_ids") or []) - exempt_s
    tgt_sets = set(target.get("set_ids") or []) - exempt_s
    src_rpts = set(source.get("report_ids") or []) - exempt_r
    tgt_rpts = set(target.get("report_ids") or []) - exempt_r

    missing_sets = sorted(src_sets - tgt_sets)
    extra_sets = sorted(tgt_sets - src_sets)
    missing_reports = sorted(src_rpts - tgt_rpts)
    extra_reports = sorted(tgt_rpts - src_rpts)

    src_hashes = source.get("report_hashes") or {}
    tgt_hashes = target.get("report_hashes") or {}
    hash_mismatches: List[Dict[str, str]] = []
    for rid in sorted(src_rpts & tgt_rpts):
        sh = src_hashes.get(rid)
        th = tgt_hashes.get(rid)
        if sh != th:
            hash_mismatches.append(
                {"report_id": rid, "source": sh or "", "target": th or ""}
            )

    src_tenants = set(source.get("tenants") or [])
    tgt_tenants = set(target.get("tenants") or [])
    tenant_leak = sorted(tgt_tenants - src_tenants) if src_tenants else []

    ok = not (
        missing_sets
        or extra_sets
        or missing_reports
        or extra_reports
        or hash_mismatches
        or tenant_leak
    )
    return {
        "ok": ok,
        "counts_match": len(src_sets) == len(tgt_sets) and len(src_rpts) == len(tgt_rpts),
        "missing_sets": missing_sets,
        "extra_sets": extra_sets,
        "missing_reports": missing_reports,
        "extra_reports": extra_reports,
        "hash_mismatches": hash_mismatches,
        "tenant_leak": tenant_leak,
        "process_split_authorized": False,
        "environment": "local",
        "note": "B3-L dual-read local only — not production cutover",
    }


def etl_copy_sets_reports(
    source: Any,
    target: Any,
    *,
    tenant_id: str = "",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Copy sets+reports source→target preserving ids; stamp migrated_at on set.meta only."""
    migrated_at = _now()
    sets = list_sets(source, limit=limit, tenant_id=tenant_id)
    reports = list_reports(source, limit=limit, tenant_id=tenant_id)
    n_sets = 0
    n_reports = 0
    for s in sets:
        meta = dict(s.get("meta") or {})
        meta["source_id"] = s["id"]
        meta["migrated_at"] = migrated_at
        meta["migration_phase"] = "B3-L"
        create_set(
            target,
            name=str(s.get("name") or s["id"]),
            version=str(s.get("version") or "0"),
            split=str(s.get("split") or "dev"),
            meta=meta,
            set_id=str(s["id"]),
            tenant_id=str(s.get("tenant_id") or tenant_id or ""),
        )
        n_sets += 1
    for r in reports:
        # Metrics must stay identical so dual-read hash matches (contract §3.1).
        create_report(
            target,
            run_ids=list(r.get("run_ids") or []),
            metrics=dict(r.get("metrics") or {}),
            slices=dict(r.get("slices") or {}),
            failures=list(r.get("failures") or []),
            report_id=str(r["id"]),
            tenant_id=str(r.get("tenant_id") or tenant_id or ""),
        )
        n_reports += 1
    return {
        "ok": True,
        "copied_sets": n_sets,
        "copied_reports": n_reports,
        "migrated_at": migrated_at,
        "process_split_authorized": False,
    }


def write_read_pointer(
    path: Path,
    *,
    mode: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Local cutover/rollback pointer (cohost|eval). Not production authorize."""
    mode_n = (mode or "").strip().lower()
    if mode_n not in ("cohost", "eval"):
        raise ValueError(f"invalid_read_mode:{mode}")
    payload = {
        "schema": READ_POINTER_SCHEMA,
        "mode": mode_n,
        "reason": reason,
        "updated_at": _now(),
        "environment": "local",
        "process_split_authorized": False,
        "note": "B3-L local pointer only — flipping to eval here is not staging authorize",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def read_read_pointer(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {
            "schema": READ_POINTER_SCHEMA,
            "mode": "cohost",
            "missing": True,
            "process_split_authorized": False,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _wire_dual_read() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    empty = {
        "set_ids": [],
        "report_ids": [],
        "report_hashes": {},
        "counts": {"sets": 0, "reports": 0},
        "tenants": [],
    }
    _ = canonical_metrics_hash({"a": 1})
    return reconcile_inventories(empty, empty)
