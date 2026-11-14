"""EVAL evidence audit status — verify tracked aggregate hashes; never accuracy.

Reads packages/aiplat-evaluation/docs/a3/evidence/evidence_manifest.v1.json
and checks on-disk SHA256 for tracked aggregates (+ optional local worksheets).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _a3_dir() -> Path:
    return _repo_root() / "packages" / "aiplat-evaluation" / "docs" / "a3"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _check_entries(
    *,
    a3: Path,
    entries: List[Any],
    verify_missing: bool,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        rel = str(ent.get("path") or "")
        expect = str(ent.get("sha256") or "")
        # Manifest paths are relative to packages/aiplat-evaluation/ (docs/a3/...).
        pkg = _repo_root() / "packages" / "aiplat-evaluation"
        path = pkg / rel if rel.startswith("docs/") else (a3 / rel)
        got = _sha256(path)
        present = got is not None
        match = bool(present and expect and got == expect)
        status = "ok" if match else ("missing" if not present else "mismatch")
        if not present and not verify_missing:
            status = "absent_ok"
        rows.append(
            {
                "id": str(ent.get("id") or rel),
                "path": rel,
                "present": present,
                "match": match,
                "status": status,
                "required_for_feature_5": bool(ent.get("required_for_feature_5")),
                "gitignored": bool(ent.get("gitignored")),
            }
        )
    return rows


def evidence_audit_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Facilitator-facing evidence audit snapshot (not an accuracy claim).

    Args:
        tenant_id: 租户 ID。
    """
    a3 = _a3_dir()
    man_path = a3 / "evidence" / "evidence_manifest.v1.json"
    man = _read_json(man_path) or {}
    tracked = man.get("tracked_aggregates") if isinstance(man.get("tracked_aggregates"), list) else []
    worksheets = man.get("local_worksheets") if isinstance(man.get("local_worksheets"), list) else []
    attest = (
        man.get("dual_human_attestation")
        if isinstance(man.get("dual_human_attestation"), dict)
        else {}
    )
    claimed = attest.get("claimed") if isinstance(attest.get("claimed"), dict) else {}

    agg_rows = _check_entries(a3=a3, entries=tracked, verify_missing=True)
    ws_rows = _check_entries(a3=a3, entries=worksheets, verify_missing=False)

    required = [r for r in agg_rows if r["required_for_feature_5"]]
    required_ok = all(r["match"] for r in required) if required else False
    all_tracked_ok = all(r["match"] for r in agg_rows) if agg_rows else False
    attest_ok = str(attest.get("status") or "") == "confirmed" and all(
        bool(claimed.get(k))
        for k in (
            "two_distinct_humans",
            "independent_blind",
            "not_script_or_ai_generated",
            "not_same_person_both_sides",
        )
    )
    feature5_audit_ready = required_ok and attest_ok

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "schema": str(man.get("schema") or "eval.scorecard.evidence_manifest.v1"),
        "manifest_path": str(man_path) if man_path.is_file() else None,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "not_accuracy_certification": True,
        "dual_human_attestation": str(attest.get("status") or "unknown"),
        "attestation_ok": attest_ok,
        "tracked_aggregates": agg_rows,
        "tracked_ok_n": sum(1 for r in agg_rows if r["match"]),
        "tracked_n": len(agg_rows),
        "required_for_feature_5_ok": required_ok,
        "all_tracked_ok": all_tracked_ok,
        "local_worksheets": ws_rows,
        "worksheets_present_n": sum(1 for r in ws_rows if r["present"]),
        "worksheets_n": len(ws_rows),
        "feature5_audit_ready": feature5_audit_ready,
        "note": (
            "Evidence audit verifies tracked aggregate SHA256 + dual-human attestation. "
            "feature5_audit_ready ≠ accuracy_claim; κ/agreement ≠ accuracy; "
            "local worksheets are gitignored and only verified when present."
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/EVIDENCE_AUDIT_V1.md",
    }
