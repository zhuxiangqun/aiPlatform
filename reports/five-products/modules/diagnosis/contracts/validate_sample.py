#!/usr/bin/env python3
"""C0 structural check for DIAGNOSIS_V1 report sample + schema file presence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / "schemas" / "diagnosis_evidence.schema.json"

SAMPLE_REPORT = {
    "schema_version": "diagnosis.report.v0",
    "case_id": "case_demo_tool_timeout",
    "summary": "Run failed after tool timeout; recommendation is escalate timeout (not auto-fix).",
    "findings": [
        {
            "id": "f1",
            "summary": "syscall tool X exceeded 30s",
            "location": "run/abc/syscall/12",
            "severity": "P0",
            "confidence": 0.9,
            "evidence_ids": ["ev_syscall_12"],
        }
    ],
    "hypotheses": [
        {
            "id": "h1",
            "root_cause": "timeout",
            "confidence": 0.85,
            "support_evidence_ids": ["ev_syscall_12", "ev_run_abc"],
            "rationale": "Duration wall clock matches tool timeout threshold",
        }
    ],
    "recommendations": [
        {
            "id": "r1",
            "action": "Increase tool timeout or split long call",
            "target_api": "/api/platform/apps/.../config",
            "auto_execute": False,
            "priority": "P1",
        }
    ],
    "evidence": [
        {
            "id": "ev_run_abc",
            "source": "aiplat",
            "kind": "run",
            "ref": "run/abc",
            "captured_at": "2026-11-01T10:00:00+00:00",
            "freshness": "fresh",
        },
        {
            "id": "ev_syscall_12",
            "source": "aiplat",
            "kind": "syscall",
            "ref": "run/abc/syscall/12",
            "captured_at": "2026-11-01T10:00:05+00:00",
            "freshness": "fresh",
        },
    ],
    "uncertainty": {"unknown": [], "stale": []},
    "accuracy_claim": False,
}


def main() -> int:
    if not SCHEMA.is_file():
        print(f"FAIL missing schema: {SCHEMA}", file=sys.stderr)
        return 1
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    report = (schema.get("$defs") or {}).get("DiagnosisReport")
    assert report, "schema missing $defs.DiagnosisReport"
    report_required = report["required"]
    missing = [k for k in report_required if k not in SAMPLE_REPORT]
    if missing:
        print(f"FAIL sample missing keys: {missing}", file=sys.stderr)
        return 1
    if SAMPLE_REPORT.get("accuracy_claim") is not False:
        print("FAIL accuracy_claim must be false", file=sys.stderr)
        return 1
    if SAMPLE_REPORT["recommendations"][0].get("auto_execute") is not False:
        print("FAIL auto_execute must be false", file=sys.stderr)
        return 1
    for f in SAMPLE_REPORT["findings"]:
        if not f.get("evidence_ids"):
            print("FAIL finding without evidence", file=sys.stderr)
            return 1
    print("OK: diagnosis C0 schema present + sample honesty constraints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
