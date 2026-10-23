"""Five-products slice: Evidence/Diagnosis MVP (KG-DIAG-01 / KG-EDGE-02).

Minimal ingest + report. Missing Pi or aiPlat evidence forces unknown/stale —
never default healthy/success.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_VALID_STATUS = frozenset({"ok", "unknown", "stale", "fail"})


def _store_root() -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    root = home / "five_products_slice" / "evidence"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    path = _store_root() / f"{ingest_id}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "ingest_id": ingest_id, "path": str(path), **rec}


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
        path = _store_root() / f"{iid}.json"
        if not path.is_file():
            return {"ok": False, "error": f"ingest not found: {iid}"}
        loaded = json.loads(path.read_text(encoding="utf-8"))

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
    }

    # Product rule: ok flag for transport vs diagnosis status
    report["diagnosis_ok"] = status == "ok"

    out = _store_root() / f"{report_id}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["path"] = str(out)
    return report


def get_slice_diagnosis_report(report_id: str) -> Dict[str, Any]:
    rid = (report_id or "").strip()
    if not rid:
        return {"ok": False, "error": "report_id required"}
    path = _store_root() / f"{rid}.json"
    if not path.is_file():
        return {"ok": False, "error": f"report not found: {rid}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ok"] = True
    return data


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
            return {"ok": False, "required": True, "error": "invalid_report_id", "report_id": rid, "detail": got.get("error")}
        # Binding a fail/unknown report is allowed for explicit reject flows;
        # "pass" decision should be caller's responsibility — we only require presence.
    return {"ok": True, "required": True, "report_ids": ids}
