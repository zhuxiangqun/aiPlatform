#!/usr/bin/env bash
# FDE Field D3 local acceptance (UAT dry-run) — environment=local only.
# Never production_signed / authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_FDE_D3_DEMO_ROOT:-/tmp/aiplat-fde-d3-uat-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_FDE_PREFIX="$DEMO_ROOT/fde"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_FDE_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
DRILL="$ROOT/packages/aiplat-fde/docs/drills"
mkdir -p "$EVID" "$DRILL"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== FDE D3 local acceptance (UAT dry-run; not production) =="
bash "$SCRIPT_DIR/d2_admin_check.sh" || fail "d2_admin"
"$PY" "$ROOT/reports/five-products/modules/fde/contracts/validate_sample.py" || fail "contracts"
bash "$SCRIPT_DIR/d1_install.sh" --smoke || fail "install"
BEFORE="$(readlink "$AIPLAT_FDE_PREFIX/current")"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "upgrade"
AFTER="$(readlink "$AIPLAT_FDE_PREFIX/current")"
[[ "$AFTER" != "$BEFORE" ]] || fail "upgrade no flip"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "runtime rollback"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "backup"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke"

OUT="$DRILL/local-fde-d3-uat-${STAMP}.json"
"$PY" - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "fde_d3_local_acceptance",
  "at": "$STAMP",
  "environment": "local",
  "uat_steps": [
    "clean_install", "contract_sample", "upgrade_n1", "runtime_rollback", "backup", "smoke"
  ],
  "production_signed": False,
  "authorize": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"
pass "FDE D3 local acceptance → $OUT"
