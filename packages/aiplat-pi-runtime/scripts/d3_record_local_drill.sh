#!/usr/bin/env bash
# Record Pi D3 local evidence (environment=local). Never authorizes d3_production.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
: "${AIPLAT_LOCAL_DRILL_ID:=pi-d3-local-${STAMP}}"
: "${AIPLAT_LOCAL_DRILL_OPERATOR:=${USER:-ops}}"
: "${AIPLAT_LOCAL_SIGN:=0}"
export AIPLAT_LOCAL_DRILL_ID AIPLAT_LOCAL_DRILL_OPERATOR AIPLAT_LOCAL_SIGN

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_LOCAL_OUT="$DRILL_DIR/local-${AIPLAT_LOCAL_DRILL_ID}.json"
export PYTHONPATH="$ROOT/scripts/lib${PYTHONPATH:+:$PYTHONPATH}"

"$PY" - <<'PY'
import os
from pathlib import Path
from aiplat_local_drill import write_local_drill

items = {
    "bundle_integrity": {"done": False, "evidence": ""},
    "ops_surface": {"done": False, "evidence": ""},
    "soc_alert_export": {"done": False, "evidence": ""},
    "n1_upgrade_rollback": {"done": False, "evidence": ""},
}
out = write_local_drill(
    out_path=Path(os.environ["AIPLAT_LOCAL_OUT"]),
    kind="pi_d3_local_drill_evidence",
    schema_version="aiplat.pi.d3.local_drill.v0",
    drill_id=os.environ["AIPLAT_LOCAL_DRILL_ID"],
    operator=os.environ["AIPLAT_LOCAL_DRILL_OPERATOR"],
    items=items,
    limitations=[
        "Local checksum/file-sink/SOC only — not production SOC egress",
        "N-1 upgrade/rollback may be D1 local path, not production channel",
        "Cannot authorize d3_production (environment=local)",
    ],
    note="Local D3 rehearsal only. Does NOT authorize d3_production_authorized.",
    authorize_flag_key="does_not_authorize_d3_production",
    local_sign=os.environ.get("AIPLAT_LOCAL_SIGN", "0").strip().lower() in {"1", "true", "yes"},
)
print("OK wrote", os.environ["AIPLAT_LOCAL_OUT"])
print(
    "NOTE: production_signed=false; local_signed=%s; d3_production NOT authorized"
    % out["local_signed"]
)
PY
