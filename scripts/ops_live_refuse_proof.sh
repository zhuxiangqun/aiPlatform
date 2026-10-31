#!/usr/bin/env bash
# Prove authorize live-evidence hard gate without mutating checklists / charts.
# Does NOT authorize cutover / split / d3_production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

echo "== ops live refuse proof (temp drills only) =="
"$PY" - <<'PY'
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

root = Path(".").resolve()
sys.path.insert(0, str(root / "scripts" / "lib"))
from aiplat_live_evidence import require_signed_live, summarize_live_drills

with tempfile.TemporaryDirectory(prefix="aiplat-live-proof-") as td:
    drill = Path(td)

    ok, s = require_signed_live(drill)
    assert ok is False and s["live_count"] == 0, s

    unsigned = drill / "live-proof-unsigned.json"
    unsigned.write_text(
        json.dumps(
            {
                "kind": "proof",
                "drill_id": "proof-unsigned",
                "production_signed": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, s = require_signed_live(drill)
    assert ok is False and s["latest"].endswith("live-proof-unsigned.json"), s

    # Newest by mtime must be signed — remove unsigned so signed is latest.
    unsigned.unlink()
    signed = drill / "live-proof-signed.json"
    signed.write_text(
        json.dumps(
            {
                "kind": "proof",
                "drill_id": "proof-signed",
                "production_signed": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, s = require_signed_live(drill)
    assert ok is True and s["production_signed"] is True, s
    assert summarize_live_drills(drill)["latest"].endswith("live-proof-signed.json")

print("PASS: ops_live_refuse_proof (unsigned→refuse logic; signed→ok; no authorize)")
print("NOTE: real *_authorize.sh still REFUSE until checklist all ✅ + signed live on track drills/")
PY
