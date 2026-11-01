#!/usr/bin/env bash
# aiPlat Central D3 local acceptance (UAT dry-run / Thin) — environment=local only.
# Never cutover authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_CENTRAL_D3_DEMO_ROOT:-/tmp/aiplat-central-d3-uat-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_CENTRAL_PREFIX="$DEMO_ROOT/central"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_CENTRAL_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
DRILL="$ROOT/packages/aiplat-central/docs/drills"
mkdir -p "$EVID" "$DRILL"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== aiPlat Central D3 local acceptance (UAT dry-run; not production) =="
bash "$SCRIPT_DIR/a2_version_check.sh" || fail "a2"
bash "$SCRIPT_DIR/d2_compat_check.sh" || fail "compat"
bash "$SCRIPT_DIR/d2_security_check.sh" || fail "security"
"$PY" "$ROOT/reports/five-products/modules/aiplat/contracts/validate_sample.py" || fail "contracts"
bash "$SCRIPT_DIR/d1_install.sh" || fail "install"
BEFORE="$(readlink "$AIPLAT_CENTRAL_PREFIX/current")"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "upgrade"
AFTER="$(readlink "$AIPLAT_CENTRAL_PREFIX/current")"
[[ "$AFTER" != "$BEFORE" ]] || fail "upgrade no flip"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "runtime rollback"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "backup"
bash "$SCRIPT_DIR/pg_ha_local_rehearsal.sh" || fail "pg_ha_local"
if bash "$SCRIPT_DIR/pg_ha_cutover_authorize.sh" authorize; then
  fail "cutover authorize must REFUSE"
fi

OUT="$DRILL/local-aiplat-d3-uat-${STAMP}.json"
"$PY" - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "aiplat_central_d3_local_acceptance",
  "at": "$STAMP",
  "environment": "local",
  "uat_steps": [
    "a2_version", "compat", "security", "contract_sample",
    "clean_install", "upgrade_n1", "runtime_rollback", "backup",
    "pg_ha_local_rehearsal", "cutover_authorize_refused"
  ],
  "cutover_authorized": False,
  "production_signed": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"
pass "aiPlat Central D3 local acceptance → $OUT"
