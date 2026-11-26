#!/usr/bin/env python3
"""Validate external-interop v1.0 schema package integrity (not implementation cert)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_DEFS = {
    "external_asset_manifest",
    "compat_verdict",
    "import_report",
    "compat_level",
    "approval_record",
}


def main() -> int:
    bundle = json.loads((ROOT / "external-interop.v1.0.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest-v1.0.json").read_text(encoding="utf-8"))
    approved = json.loads(
        (ROOT / "conformance" / "approval-record-v1.0.approved.json").read_text(encoding="utf-8")
    )
    defs = set((bundle.get("$defs") or {}).keys())
    missing = REQUIRED_DEFS - defs
    if missing:
        print("FAIL missing $defs:", sorted(missing))
        return 1
    if manifest.get("status") != "approved" or approved.get("status") != "approved":
        print("FAIL status")
        return 1
    checklist = (ROOT / "conformance-checklist.yaml").read_text(encoding="utf-8")
    for xid in ("X01", "X06"):
        if xid not in checklist:
            print("FAIL checklist missing", xid)
            return 1
    print("OK external-interop v1.0 schemas package")
    return 0


if __name__ == "__main__":
    sys.exit(main())
