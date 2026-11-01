#!/usr/bin/env python3
"""Pi A1/D1 contract sample — healthz only (zero-dep fallback)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCHEMA = ROOT / "packages/aiplat-pi-runtime/contracts/schemas/healthz.schema.json"
HEALTHZ = {
    "status": "ok",
    "version": "0.1.0",
    "product_id": "pi",
    "capability_id": "pi",
    "deploy_unit": "edge",
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
    for k, v in sample.items():
        if k in props and "const" in props[k] and v != props[k]["const"]:
            raise SystemExit(f"FAIL {k} const mismatch")
    print(f"OK fallback {schema_path.name}")


def main() -> int:
    if not SCHEMA.is_file():
        print(f"FAIL missing {SCHEMA}", file=sys.stderr)
        return 2
    _check(HEALTHZ, SCHEMA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
