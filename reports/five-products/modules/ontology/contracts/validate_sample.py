#!/usr/bin/env python3
"""Ontology A1 — healthz + ontology.api.v0 sample validator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTHZ = {
    "status": "ok",
    "version": "0.0.0",
    "product_id": "ontology",
    "capability_id": "ontology",
    "deploy_unit": "central",
    "domains": 0,
    "mode": "read_only",
}
API = {
    "schema_version": "ontology.api.v0",
    "kind": "query_result",
    "domain_id": "example",
    "payload": {"entities": [], "relations": []},
    "refs": [],
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
        raise SystemExit(f"FAIL product_id={sample.get('product_id')}")
    sv = props.get("schema_version", {}).get("const")
    if sv and sample.get("schema_version") != sv:
        raise SystemExit(f"FAIL schema_version={sample.get('schema_version')}")
    print(f"OK fallback {schema_path.name}")


def main() -> int:
    _check(HEALTHZ, HERE / "schemas" / "healthz.schema.json")
    _check(API, HERE / "schemas" / "ontology_api.schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
