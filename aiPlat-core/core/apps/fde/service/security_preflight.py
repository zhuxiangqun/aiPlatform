"""FDE Phase 4A — preflight security dry-run summary store (read-only evidence).

Does NOT invent severity enums or a parallel security pipeline.
Calls go through CoreFacade.run_security_review_dry from the platform API layer.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _dir() -> Path:
    d = _home() / "fde_security_preflight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def summarize_security_dry_run(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract read-only summary for FDE Evidence display (no severity remapping)."""
    report = result.get("security_report") if isinstance(result.get("security_report"), dict) else {}
    critique = result.get("security_critique") if isinstance(result.get("security_critique"), dict) else {}
    evidence = result.get("security_evidence") if isinstance(result.get("security_evidence"), dict) else {}
    findings = report.get("findings") or critique.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    # Preserve upstream severity/status fields as-is
    slim_findings: List[Dict[str, Any]] = []
    for f in findings[:50]:
        if not isinstance(f, dict):
            continue
        slim_findings.append(
            {
                "id": str(f.get("id") or f.get("finding_id") or "")[:80],
                "title": str(f.get("title") or f.get("summary") or f.get("name") or "")[:200],
                "severity": f.get("severity"),  # unchanged from security pipeline
                "status": f.get("status"),
                "evidence_ref": f.get("evidence_ref") or f.get("evidence_path") or "",
            }
        )
    return {
        "phase": result.get("phase") or "B",
        "status": result.get("status") or "ok",
        "finding_count": len(slim_findings),
        "findings": slim_findings,
        "evidence_enabled": bool(evidence.get("enabled")),
        "evidence_ref": evidence.get("evidence_path")
        or evidence.get("path")
        or evidence.get("regression_evidence_path")
        or "",
        "report_keys": sorted(list(report.keys()))[:30] if isinstance(report, dict) else [],
    }


def save_preflight_run(
    *,
    dry_run: Dict[str, Any],
    actor: str = "fde_engineer",
    phase_c_enabled: bool = False,
    max_paths: int = 20,
) -> Dict[str, Any]:
    """Persist last preflight summary under AIPLAT_HOME (Evidence store pointer)."""
    run_id = f"fde_sec_{uuid.uuid4().hex[:12]}"
    summary = summarize_security_dry_run(dry_run if isinstance(dry_run, dict) else {})
    record = {
        "run_id": run_id,
        "label": "FDE 4A = security B/C",
        "actor": actor,
        "phase_c_enabled": bool(phase_c_enabled),
        "max_paths": int(max_paths or 20),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        # Keep compact raw pointers only (not full graph dump)
        "raw_status": dry_run.get("status") if isinstance(dry_run, dict) else None,
        "raw_phase": dry_run.get("phase") if isinstance(dry_run, dict) else None,
    }
    fp = _dir() / f"{run_id}.json"
    fp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = _dir() / "latest.json"
    latest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def get_latest_preflight() -> Optional[Dict[str, Any]]:
    fp = _dir() / "latest.json"
    if not fp.is_file():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def list_preflight_runs(limit: int = 10) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for fp in sorted(_dir().glob("fde_sec_*.json"), reverse=True):
        try:
            rows.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows
