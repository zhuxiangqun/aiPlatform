#!/usr/bin/env bash
# Record Pi D3 live drill evidence. Does NOT authorize d3_production.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$DRILL_DIR"
: "${AIPLAT_LIVE_DRILL_ID:?set AIPLAT_LIVE_DRILL_ID}"
: "${AIPLAT_LIVE_DRILL_ENV:?set AIPLAT_LIVE_DRILL_ENV}"
: "${AIPLAT_LIVE_DRILL_OPERATOR:?set AIPLAT_LIVE_DRILL_OPERATOR}"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_LIVE_OUT="$DRILL_DIR/live-${AIPLAT_LIVE_DRILL_ID}.json"

"$PY" - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

items = {
    "bundle_integrity": {"done": False, "evidence": ""},
    "ops_surface": {"done": False, "evidence": ""},
    "soc_alert_export": {"done": False, "evidence": ""},
    "n1_upgrade_rollback": {"done": False, "evidence": ""},
}
items_file = os.environ.get("AIPLAT_LIVE_DRILL_ITEMS_FILE", "")
if items_file and Path(items_file).is_file():
    items.update(json.loads(Path(items_file).read_text(encoding="utf-8")))

out = {
    "kind": "pi_d3_live_drill_evidence",
    "schema_version": "aiplat.pi.d3.live_drill.v0",
    "drill_id": os.environ["AIPLAT_LIVE_DRILL_ID"],
    "environment": os.environ["AIPLAT_LIVE_DRILL_ENV"],
    "operator": os.environ["AIPLAT_LIVE_DRILL_OPERATOR"],
    "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "production_signed": False,
    "items": items,
    "does_not_authorize_d3_production": True,
}
path = Path(os.environ["AIPLAT_LIVE_OUT"])
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("OK wrote", path)
PY
