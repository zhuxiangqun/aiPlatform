#!/usr/bin/env python3
"""Evaluation A1 — Eval Protocol v0 + healthz sample validator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = {
    "schema_version": "eval.protocol.v0",
    "task": {
        "id": "eval-sample-001",
        "target_kind": "skill",
        "target_ref": "fixture-skill",
        "suite": "smoke",
    },
    "status": "passed",
    "metrics": {"pass_rate": 1.0},
    "report": {"summary": "sample", "score": 1.0, "gate": "pass"},
    "evidence_refs": [],
}
HEALTHZ = {
    "status": "ok",
    "version": "0.0.0",
    "product_id": "evaluation",
    "capability_id": "evaluation",
    "deploy_unit": "central",
    "protocol": "eval.protocol.v0",
}


def _check(sample: dict, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        import jsonschema

        jsonschema.validate(sample, schema)
        print(f"OK jsonschema {schema_path.name}")
        return
    except ImportError:
        pass
    for k in schema.get("required") or []:
        if k not in sample:
            raise SystemExit(f"FAIL missing {k} in {schema_path.name}")
    props = schema.get("properties") or {}
    const = props.get("product_id", {}).get("const")
    if const and sample.get("product_id") != const:
        raise SystemExit(f"FAIL product_id in {schema_path.name}")
    sv = props.get("schema_version", {}).get("const")
    if sv and sample.get("schema_version") != sv:
        raise SystemExit(f"FAIL schema_version in {schema_path.name}")
    print(f"OK fallback {schema_path.name}")


def main() -> int:
    _check(SAMPLE, HERE / "schemas" / "eval_protocol.schema.json")
    _check(HEALTHZ, HERE / "schemas" / "healthz.schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
