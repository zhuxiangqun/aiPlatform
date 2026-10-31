#!/usr/bin/env bash
# Record Evaluation A3 local evidence (environment=local). Never authorizes process split.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-evaluation/docs/a3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
: "${AIPLAT_LOCAL_DRILL_ID:=evaluation-a3-local-${STAMP}}"
: "${AIPLAT_LOCAL_DRILL_OPERATOR:=${USER:-ops}}"
: "${AIPLAT_LOCAL_SIGN:=0}"
export AIPLAT_LOCAL_DRILL_ID AIPLAT_LOCAL_DRILL_OPERATOR AIPLAT_LOCAL_SIGN

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_LOCAL_OUT="$DRILL_DIR/local-${AIPLAT_LOCAL_DRILL_ID}.json"
export PYTHONPATH="$ROOT/scripts/lib${PYTHONPATH:+:$PYTHONPATH}"
"$PY" - <<PY
import os
from pathlib import Path
from aiplat_local_drill import write_local_drill

items = {
    "backup_restore_rollback": {"done": False, "evidence": ""},
    "healthz_protocol": {"done": False, "evidence": ""},
}
out = write_local_drill(
    out_path=Path(os.environ["AIPLAT_LOCAL_OUT"]),
    kind="evaluation_a3_local_drill_evidence",
    schema_version="aiplat.evaluation.a3.local_drill.v0",
    drill_id=os.environ["AIPLAT_LOCAL_DRILL_ID"],
    operator=os.environ["AIPLAT_LOCAL_DRILL_OPERATOR"],
    items=items,
    limitations=[
        "Local SQLite+prefix only — not production eval store",
        "healthz may be schema/sample validate only (not production HTTP)",
        "Cannot authorize process_split (environment=local)",
    ],
    note="Local A3 rehearsal only. Does NOT authorize process split.",
    authorize_flag_key="does_not_authorize_process_split",
    local_sign=os.environ.get("AIPLAT_LOCAL_SIGN", "0").strip().lower() in {"1", "true", "yes"},
)
print("OK wrote", os.environ["AIPLAT_LOCAL_OUT"])
print("NOTE: production_signed=false; local_signed=%s; process_split NOT authorized" % out["local_signed"])
PY
