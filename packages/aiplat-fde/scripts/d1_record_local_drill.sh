#!/usr/bin/env bash
# Record FDE Field D1 local evidence (environment=local). Never production authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-fde/docs/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
: "${AIPLAT_LOCAL_DRILL_ID:=fde-field-local-${STAMP}}"
: "${AIPLAT_LOCAL_DRILL_OPERATOR:=${USER:-ops}}"
: "${AIPLAT_LOCAL_SIGN:=0}"
export AIPLAT_LOCAL_DRILL_ID AIPLAT_LOCAL_DRILL_OPERATOR AIPLAT_LOCAL_SIGN

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_LOCAL_OUT="$DRILL_DIR/local-${AIPLAT_LOCAL_DRILL_ID}.json"
export PYTHONPATH="$ROOT/scripts/lib${PYTHONPATH:+:$PYTHONPATH}"

"$PY" - <<'PY'
import os
from pathlib import Path
from aiplat_local_drill import write_local_drill

items = {
    "install_meta": {"done": False, "evidence": ""},
    "smoke_contracts": {"done": False, "evidence": ""},
    "backup": {"done": False, "evidence": ""},
    "rollback": {"done": False, "evidence": ""},
}
out = write_local_drill(
    out_path=Path(os.environ["AIPLAT_LOCAL_OUT"]),
    kind="fde_field_local_drill_evidence",
    schema_version="aiplat.fde.field.local_drill.v0",
    drill_id=os.environ["AIPLAT_LOCAL_DRILL_ID"],
    operator=os.environ["AIPLAT_LOCAL_DRILL_OPERATOR"],
    items=items,
    limitations=[
        "Local Field prefix only — not customer-site soak",
        "Smoke uses CoreFacade healthz shape; optional live probe is AIPLAT_FDE_SMOKE_LIVE=1",
        "Does not authorize production field rollout beyond ADR path",
    ],
    note="Local Field D1 install/meta/backup/rollback. production_signed always false.",
    authorize_flag_key="does_not_authorize_production_field_extra",
    local_sign=os.environ.get("AIPLAT_LOCAL_SIGN", "0").strip().lower() in {"1", "true", "yes"},
)
print("OK wrote", os.environ["AIPLAT_LOCAL_OUT"])
print("NOTE: production_signed=false; local_signed=%s" % out["local_signed"])
PY
