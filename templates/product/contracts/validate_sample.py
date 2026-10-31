#!/usr/bin/env python3
"""Minimal contract sample: validate a healthz payload against JSON Schema (P0)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent / "schemas" / "healthz.schema.json"
SAMPLE = {"status": "ok", "version": "0.0.0", "product_id": "pi"}


def main() -> int:
    try:
        import jsonschema
    except ImportError:
        # Zero-dep fallback: required keys + enum only
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        required = schema.get("required") or []
        for k in required:
            if k not in SAMPLE:
                print(f"FAIL missing {k}", file=sys.stderr)
                return 1
        status = SAMPLE.get("status")
        allowed = schema["properties"]["status"].get("enum") or []
        if status not in allowed:
            print(f"FAIL status={status}", file=sys.stderr)
            return 1
        print("OK (fallback validator)")
        return 0

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(SAMPLE, schema)
    print("OK (jsonschema)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
