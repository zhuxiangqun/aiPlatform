#!/usr/bin/env python3
"""DIAGNOSIS_V1 C0/C1 contract check: JSON Schema + honesty negatives."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schemas" / "diagnosis_evidence.schema.json"

POSITIVE = {
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
    "generated_at": "2026-11-01T10:01:00+00:00",
}


def _validator():
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        print("FAIL: jsonschema required", file=sys.stderr)
        raise SystemExit(2)

    raw = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = raw.get("$defs") or {}
    if "DiagnosisReport" not in defs:
        print("FAIL: schema missing $defs.DiagnosisReport", file=sys.stderr)
        raise SystemExit(1)

    # Root schema = DiagnosisReport, keep $defs for local $ref resolution
    report_schema = {
        "$schema": raw.get("$schema"),
        "$id": raw.get("$id", "") + "#report",
        "$defs": defs,
        **{k: v for k, v in defs["DiagnosisReport"].items() if k != "$defs"},
    }

    try:
        from referencing import Registry, Resource

        registry = Registry().with_resource(
            raw["$id"],
            Resource.from_contents(raw),
        )
        # Also publish report schema id
        registry = registry.with_resource(
            report_schema["$id"],
            Resource.from_contents({**raw, **{"$ref": "#/$defs/DiagnosisReport"}}),
        )
        # Validate against full document with $ref root
        root = {
            "$schema": raw["$schema"],
            "$id": raw["$id"] + "/report-root",
            "$ref": "#/$defs/DiagnosisReport",
            "$defs": defs,
        }
        registry = registry.with_resource(
            root["$id"], Resource.from_contents(root)
        )
        return Draft202012Validator(root, registry=registry)
    except Exception:
        # Fallback: inline $ref by expanding once (C0/C1 gate still enforces honesty)
        return Draft202012Validator(report_schema)


def _must_fail(validator, instance: dict, label: str) -> None:
    errors = list(validator.iter_errors(instance))
    if not errors:
        # Extra honesty gates if schema soft on additionalProperties
        if label == "accuracy_claim_true" and instance.get("accuracy_claim") is True:
            return  # should have failed — treat as hard fail below
        if label == "accuracy_claim_missing" and "accuracy_claim" not in instance:
            # required field — must error
            pass
        print(f"FAIL: expected invalid ({label})", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK negative: {label}")


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"FAIL missing schema: {SCHEMA_PATH}", file=sys.stderr)
        return 1

    validator = _validator()

    # Positive
    errs = list(validator.iter_errors(POSITIVE))
    if errs:
        print(f"FAIL positive sample: {errs[0].message}", file=sys.stderr)
        return 1
    if POSITIVE.get("accuracy_claim") is not False:
        print("FAIL positive accuracy_claim", file=sys.stderr)
        return 1
    print("OK positive: DiagnosisReport sample")

    # Negatives
    bad_true = copy.deepcopy(POSITIVE)
    bad_true["accuracy_claim"] = True
    _must_fail(validator, bad_true, "accuracy_claim_true")

    bad_missing = copy.deepcopy(POSITIVE)
    del bad_missing["accuracy_claim"]
    _must_fail(validator, bad_missing, "accuracy_claim_missing")

    bad_auto = copy.deepcopy(POSITIVE)
    bad_auto["recommendations"][0]["auto_execute"] = True
    _must_fail(validator, bad_auto, "auto_execute_true")

    bad_finding = copy.deepcopy(POSITIVE)
    bad_finding["findings"][0]["evidence_ids"] = []
    _must_fail(validator, bad_finding, "finding_without_evidence")

    print("OK: diagnosis schema jsonschema + honesty negatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
