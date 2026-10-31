#!/usr/bin/env bash
# Record PG/HA local-staging evidence (environment=local).
# Never sets production_signed=true. Never authorizes cutover.
# Writes local-*.json (authorize only reads live-*.json).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-central/docs/pg_ha/drills"
mkdir -p "$DRILL_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
: "${AIPLAT_LOCAL_DRILL_ID:=pgha-local-${STAMP}}"
: "${AIPLAT_LOCAL_DRILL_OPERATOR:=${USER:-ops}}"
# Force local — refuse staging/prod labels on this path.
ENV_NAME="local"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

export AIPLAT_LOCAL_OUT="$DRILL_DIR/local-${AIPLAT_LOCAL_DRILL_ID}.json"
export AIPLAT_LOCAL_DRILL_ID AIPLAT_LOCAL_DRILL_OPERATOR
export AIPLAT_LOCAL_ENV="$ENV_NAME"
export AIPLAT_LOCAL_SIGN="${AIPLAT_LOCAL_SIGN:-0}"
export AIPLAT_LOCAL_ITEMS_FILE="${AIPLAT_LOCAL_DRILL_ITEMS_FILE:-}"
export AIPLAT_LOCAL_LIMITATIONS="${AIPLAT_LOCAL_LIMITATIONS:-}"

"$PY" - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

items = {
    "oidc_full": {"done": False, "evidence": ""},
    "pg_migration": {"done": False, "evidence": ""},
    "backup_restore": {"done": False, "evidence": ""},
    "ha_failover": {"done": False, "evidence": ""},
    "rollback": {"done": False, "evidence": ""},
}
items_file = os.environ.get("AIPLAT_LOCAL_ITEMS_FILE", "")
if items_file and Path(items_file).is_file():
    items.update(json.loads(Path(items_file).read_text(encoding="utf-8")))

default_limits = [
    "Single-host Docker/VM — not multi-node HA / VIP / shared storage",
    "Not cloud managed Postgres / PITR parity",
    "Not production load or latency proof",
    "Cannot authorize cutover (environment=local)",
]
extra = [x.strip() for x in (os.environ.get("AIPLAT_LOCAL_LIMITATIONS") or "").split(";") if x.strip()]
limitations = default_limits + extra

local_signed = os.environ.get("AIPLAT_LOCAL_SIGN", "0").strip() in {"1", "true", "yes"}
# Only allow local_signed when every item done + non-empty evidence
if local_signed:
    for k, v in items.items():
        if not (isinstance(v, dict) and v.get("done") and str(v.get("evidence") or "").strip()):
            local_signed = False
            break

out = {
    "kind": "pg_ha_local_drill_evidence",
    "schema_version": "aiplat.pg_ha.local_drill.v0",
    "drill_id": os.environ["AIPLAT_LOCAL_DRILL_ID"],
    "environment": "local",
    "operator": os.environ["AIPLAT_LOCAL_DRILL_OPERATOR"],
    "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "production_signed": False,
    "local_signed": local_signed,
    "items": items,
    "limitations": limitations,
    "note": (
        "Local staging / zero-budget rehearsal only. "
        "Does NOT authorize cutover. Use live-*.json + staging for authorize."
    ),
    "does_not_authorize_cutover": True,
}
path = Path(os.environ["AIPLAT_LOCAL_OUT"])
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("OK wrote", path)
print("NOTE: production_signed=false; local_signed=%s; cutover NOT authorized" % local_signed)
PY
