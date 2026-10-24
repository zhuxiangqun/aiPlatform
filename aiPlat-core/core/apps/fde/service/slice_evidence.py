"""Five-products slice: Evidence/Diagnosis MVP (KG-DIAG-01 / KG-EDGE-02).

Minimal ingest + report. Missing Pi or aiPlat evidence forces unknown/stale —
never default healthy/success.

Storage (MB-03 / Gate2): default SQLite under AIPLAT_HOME; set
AIPLAT_SLICE_EVIDENCE_STORE=file to force JSON files (rollback).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_VALID_STATUS = frozenset({"ok", "unknown", "stale", "fail"})


def _store_mode() -> str:
    raw = (os.getenv("AIPLAT_SLICE_EVIDENCE_STORE") or "sqlite").strip().lower()
    return "file" if raw in ("file", "json", "fs") else "sqlite"


def _store_root() -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    root = home / "five_products_slice" / "evidence"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _db_path() -> Path:
    return _store_root() / "evidence.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS slice_records (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            scenario_id TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_slice_records_kind ON slice_records(kind)"
    )
    return conn


def _put_record(kind: str, record_id: str, scenario_id: str, payload: Dict[str, Any]) -> str:
    """Persist record; returns storage path or db URI for response."""
    if _store_mode() == "file":
        path = _store_root() / f"{record_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    blob = json.dumps(payload, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO slice_records (id, kind, scenario_id, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (record_id, kind, scenario_id or "", blob, _now()),
        )
        conn.commit()
    return f"sqlite:{_db_path()}#{record_id}"


def _get_record(record_id: str) -> Optional[Dict[str, Any]]:
    rid = (record_id or "").strip()
    if not rid:
        return None

    # Prefer active backend; fall back to the other for migration/read.
    if _store_mode() == "file":
        path = _store_root() / f"{rid}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        with _connect() as conn:
            row = conn.execute(
                "SELECT payload FROM slice_records WHERE id = ?", (rid,)
            ).fetchone()
        if row:
            return json.loads(row["payload"])
        return None

    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM slice_records WHERE id = ?", (rid,)
        ).fetchone()
    if row:
        return json.loads(row["payload"])
    path = _store_root() / f"{rid}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def ingest_slice_evidence(
    *,
    scenario_id: str,
    run_id: str = "",
    bundle_version: str = "",
    runtime_version: str = "",
    events: Optional[List[Dict[str, Any]]] = None,
    asset_versions: Optional[Dict[str, Any]] = None,
    aiplat_reachable: bool = True,
) -> Dict[str, Any]:
    """Persist one evidence batch. Returns ingest record id."""
    sid = (scenario_id or "").strip()
    if not sid:
        return {"ok": False, "error": "scenario_id required"}

    ingest_id = f"ing-{uuid.uuid4().hex[:12]}"
    rec = {
        "ingest_id": ingest_id,
        "scenario_id": sid,
        "run_id": (run_id or "").strip(),
        "bundle_version": (bundle_version or "").strip(),
        "runtime_version": (runtime_version or "").strip(),
        "events": list(events or []),
        "asset_versions": dict(asset_versions or {}),
        "aiplat_reachable": bool(aiplat_reachable),
        "ingested_at": _now(),
    }
    storage = _put_record("ingest", ingest_id, sid, rec)
    return {"ok": True, "ingest_id": ingest_id, "path": storage, "store": _store_mode(), **rec}


def _derive_status(
    *,
    run_id: str,
    bundle_version: str,
    events: List[Any],
    asset_versions: Dict[str, Any],
    aiplat_reachable: bool,
) -> str:
    has_pi = bool(run_id) or bool(events)
    has_bundle = bool(bundle_version) or bool(asset_versions.get("bundle_version"))
    if not has_pi and not has_bundle:
        return "fail"
    if not has_pi or not has_bundle:
        return "unknown"
    if not aiplat_reachable:
        return "stale"
    return "ok"


def build_slice_diagnosis_report(
    *,
    scenario_id: str,
    ingest_id: str = "",
    run_id: str = "",
    bundle_version: str = "",
    runtime_version: str = "",
    events: Optional[List[Dict[str, Any]]] = None,
    asset_versions: Optional[Dict[str, Any]] = None,
    aiplat_reachable: bool = True,
) -> Dict[str, Any]:
    """Build a diagnosis report. Loads ingest_id when provided."""
    sid = (scenario_id or "").strip()
    if not sid:
        return {"ok": False, "error": "scenario_id required"}

    loaded: Dict[str, Any] = {}
    iid = (ingest_id or "").strip()
    if iid:
        loaded = _get_record(iid) or {}
        if not loaded:
            return {"ok": False, "error": f"ingest not found: {iid}"}

    run_id = (run_id or loaded.get("run_id") or "").strip()
    bundle_version = (bundle_version or loaded.get("bundle_version") or "").strip()
    runtime_version = (runtime_version or loaded.get("runtime_version") or "").strip()
    events_l = list(events if events is not None else loaded.get("events") or [])
    assets = dict(asset_versions if asset_versions is not None else loaded.get("asset_versions") or {})
    if iid and loaded and "aiplat_reachable" in loaded:
        reachable = bool(loaded.get("aiplat_reachable"))
    else:
        reachable = bool(aiplat_reachable)

    status = _derive_status(
        run_id=run_id,
        bundle_version=bundle_version,
        events=events_l,
        asset_versions=assets,
        aiplat_reachable=reachable,
    )
    if status not in _VALID_STATUS:
        status = "unknown"

    report_id = f"rep-{uuid.uuid4().hex[:12]}"
    evidence_refs = []
    if run_id:
        evidence_refs.append({"kind": "pi_run", "id": run_id})
    if bundle_version:
        evidence_refs.append({"kind": "bundle_version", "id": bundle_version})
    if iid:
        evidence_refs.append({"kind": "ingest", "id": iid})

    freshness = "fresh" if status == "ok" else ("stale" if status == "stale" else "incomplete")

    report = {
        "ok": True,
        "report_id": report_id,
        "scenario_id": sid,
        "status": status,
        "run_id": run_id,
        "trace_id": "",
        "bundle_version": bundle_version,
        "runtime_version": runtime_version,
        "evidence_refs": evidence_refs,
        "freshness": freshness,
        "asset_versions": assets,
        "event_count": len(events_l),
        "created_at": _now(),
        "rule": (
            "Missing Pi run/events or bundle/asset version → unknown/fail; "
            "aiPlat unreachable with otherwise complete evidence → stale; "
            "never default to healthy/success."
        ),
        "diagnosis_ok": status == "ok",
    }

    storage = _put_record("report", report_id, sid, report)
    report["path"] = storage
    report["store"] = _store_mode()
    return report


def get_slice_diagnosis_report(report_id: str) -> Dict[str, Any]:
    rid = (report_id or "").strip()
    if not rid:
        return {"ok": False, "error": "report_id required"}
    data = _get_record(rid)
    if not data:
        return {"ok": False, "error": f"report not found: {rid}"}
    data["ok"] = True
    return data


def ingest_slice_evidence_from_jsonl(
    *,
    path: str,
    scenario_id: str = "",
    aiplat_reachable: bool = True,
) -> Dict[str, Any]:
    """Ingest MB-05 Pi emit JSONL (one JSON object per line) into evidence store."""
    p = Path((path or "").strip())
    if not p.is_file():
        return {"ok": False, "error": f"jsonl not found: {p}"}

    events: List[Dict[str, Any]] = []
    run_id = ""
    bundle_version = ""
    runtime_version = ""
    sid = (scenario_id or "").strip()

    for line in p.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"invalid jsonl: {exc}", "path": str(p)}
        if not isinstance(obj, dict):
            return {"ok": False, "error": "jsonl line must be object", "path": str(p)}
        events.append(obj)
        if not run_id:
            run_id = str(obj.get("run_id") or "").strip()
        if not bundle_version:
            bundle_version = str(obj.get("bundle_version") or "").strip()
        if not runtime_version:
            runtime_version = str(obj.get("runtime_version") or "").strip()
        if not sid:
            sid = str(obj.get("scenario_id") or "").strip()

    if not sid:
        return {"ok": False, "error": "scenario_id required (arg or jsonl)"}
    if not events:
        return {"ok": False, "error": "empty jsonl", "path": str(p)}

    assets: Dict[str, Any] = {}
    if bundle_version:
        assets["bundle_version"] = bundle_version

    return ingest_slice_evidence(
        scenario_id=sid,
        run_id=run_id,
        bundle_version=bundle_version,
        runtime_version=runtime_version or "pi-thin-emit",
        events=events,
        asset_versions=assets,
        aiplat_reachable=aiplat_reachable,
    )


def slice_signoff_requires_report(body: Dict[str, Any]) -> bool:
    """Whether acceptance signoff must bind a diagnosis report_id."""
    if os.getenv("AIPLAT_FDE_REQUIRE_DIAG_REPORT_FOR_SLICE", "1").strip() == "0":
        return False
    if body.get("for_slice") is True or str(body.get("for_slice") or "").strip().lower() in ("1", "true", "yes"):
        return True
    sid = str(body.get("scenario_id") or body.get("spec_id") or "").strip()
    if sid.startswith("fp-"):
        return True
    if body.get("evidence_report_ids") is not None:
        return True
    return False


def validate_slice_signoff_reports(body: Dict[str, Any]) -> Dict[str, Any]:
    """Return {ok, error?, report_ids} for slice acceptance binding."""
    if not slice_signoff_requires_report(body):
        return {"ok": True, "required": False, "report_ids": []}

    raw = body.get("evidence_report_ids")
    if raw is None and body.get("report_id"):
        raw = [body.get("report_id")]
    if not isinstance(raw, list) or not raw:
        return {
            "ok": False,
            "required": True,
            "error": "slice_signoff_requires_evidence_report_ids",
            "detail": "for_slice/fp-* signoff requires evidence_report_ids with valid report_id",
        }

    ids = [str(x).strip() for x in raw if str(x).strip()]
    if not ids:
        return {"ok": False, "required": True, "error": "empty_evidence_report_ids"}

    for rid in ids:
        got = get_slice_diagnosis_report(rid)
        if not got.get("ok") or got.get("error"):
            return {
                "ok": False,
                "required": True,
                "error": "invalid_report_id",
                "report_id": rid,
                "detail": got.get("error"),
            }
    return {"ok": True, "required": True, "report_ids": ids}
