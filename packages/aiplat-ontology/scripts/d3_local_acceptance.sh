#!/usr/bin/env bash
# Ontology D3 local acceptance (UAT dry-run / cohost) — environment=local only.
# Never process_split authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_ONTOLOGY_D3_DEMO_ROOT:-/tmp/aiplat-ontology-d3-uat-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_ONTOLOGY_PREFIX="$DEMO_ROOT/ontology"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_ONTOLOGY_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
DRILL="$ROOT/packages/aiplat-ontology/docs/drills"
mkdir -p "$EVID" "$DRILL"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Ontology D3 local acceptance (UAT dry-run; not production) =="
bash "$SCRIPT_DIR/d2_admin_check.sh" || fail "d2_admin"
"$PY" "$ROOT/reports/five-products/modules/ontology/contracts/validate_sample.py" || fail "contracts"
bash "$SCRIPT_DIR/d1_install.sh" || fail "install"
BEFORE="$(readlink "$AIPLAT_ONTOLOGY_PREFIX/current")"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "upgrade"
AFTER="$(readlink "$AIPLAT_ONTOLOGY_PREFIX/current")"
[[ "$AFTER" != "$BEFORE" ]] || fail "upgrade no flip"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "runtime rollback"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "backup"
# heavy TestClient smoke optional
if [[ "${AIPLAT_D3_INCLUDE_SMOKE:-0}" == "1" ]]; then
  bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke"
fi
bash "$SCRIPT_DIR/a3_local_rehearsal.sh" || fail "a3_local_rehearsal"
if bash "$SCRIPT_DIR/a3_split_authorize.sh" authorize; then
  fail "a3_split_authorize must REFUSE"
fi

OUT="$DRILL/local-ontology-d3-uat-${STAMP}.json"
"$PY" - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "ontology_d3_local_acceptance",
  "at": "$STAMP",
  "environment": "local",
  "delivery_mode": "cohost",
  "uat_steps": [
    "clean_install", "contract_sample", "upgrade_n1", "runtime_rollback",
    "backup", "a3_local_rehearsal", "split_authorize_refused"
  ],
  "process_split_authorized": False,
  "production_signed": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"
pass "Ontology D3 local acceptance → $OUT"
