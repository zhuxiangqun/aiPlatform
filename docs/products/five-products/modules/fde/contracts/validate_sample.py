#!/usr/bin/env python3
"""FDE A1 contract samples — healthz + evidence export (zero-dep fallback)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTHZ = {
    "status": "ok",
    "version": "0.0.0",
    "product_id": "fde",
    "capability_id": "fde",
    "deploy_unit": "field",
    "signoff": "POST /api/platform/apps/fde/acceptance/signoff",
}
EVIDENCE = {
    "schema_version": "fde.evidence.v0",
    "scenario_id": "fp-customer-lock-service-bundle-pi-diag-001",
    "exported_at": "2026-10-29T00:00:00Z",
    "report_id": "rep-sample",
    "items": [{"kind": "diagnosis_report", "ref": "rep-sample"}],
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
    st = props.get("status", {}).get("enum")
    if st and sample.get("status") not in st:
        raise SystemExit(f"FAIL status={sample.get('status')}")
    pid = props.get("product_id", {}).get("const")
    if pid and sample.get("product_id") != pid:
        raise SystemExit(f"FAIL product_id={sample.get('product_id')}")
    print(f"OK fallback {schema_path.name}")


def main() -> int:
    _check(HEALTHZ, HERE / "schemas" / "healthz.schema.json")
    _check(EVIDENCE, HERE / "schemas" / "evidence_export.schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
