#!/usr/bin/env bash
# FDE Field D1 local regression — install/meta/smoke/backup/rollback (environment=local).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_FDE_D1_DEMO_ROOT:-/tmp/aiplat-fde-d1-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_FDE_PREFIX="$DEMO_ROOT/fde"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_FDE_PREFIX"
EVID_DIR="$ROOT/reports/five-products/ops/evidence"
RUNLOG="$ROOT/reports/five-products/ops/FDE_FIELD_LOCAL_REGRESSION.md"
mkdir -p "$EVID_DIR"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== FDE Field D1 local regression (environment=local) =="
echo "DEMO_ROOT=$DEMO_ROOT"

bash "$SCRIPT_DIR/d1_install.sh" --smoke || fail "d1_install --smoke"
[[ -f "$AIPLAT_FDE_PREFIX/INSTALL_META.json" ]] || fail "INSTALL_META missing"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "d1_smoke"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "d1_backup"
# Corrupt then restore from latest backup tarball (Field rollback path)
BACKUP_TGZ="$(ls -1t "$AIPLAT_FDE_PREFIX/backups"/*.tgz 2>/dev/null | head -1 || true)"
[[ -n "$BACKUP_TGZ" ]] || fail "no backup tgz"
# touch a marker then roll back via --backup
echo "pre-rollback" >"$AIPLAT_FDE_PREFIX/logs/rollback-marker.txt"
bash "$SCRIPT_DIR/d1_rollback.sh" --backup "$BACKUP_TGZ" || fail "d1_rollback --backup"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke after rollback"

ITEMS="$(mktemp)"
cat >"$ITEMS" <<JSON
{
  "install_meta": {"done": true, "evidence": "d1_install wrote INSTALL_META.json production_field=true (local hermetic prefix)"},
  "smoke_contracts": {"done": true, "evidence": "d1_smoke contracts + CoreFacade healthz (local)"},
  "backup": {"done": true, "evidence": "d1_backup under \$AIPLAT_FDE_PREFIX/backups (local)"},
  "rollback": {"done": true, "evidence": "d1_rollback + smoke (local)"}
}
JSON
export AIPLAT_LOCAL_DRILL_ITEMS_FILE="$ITEMS"
export AIPLAT_LOCAL_DRILL_ID="fde-field-local-${STAMP}"
export AIPLAT_LOCAL_DRILL_OPERATOR="${USER:-ops}"
export AIPLAT_LOCAL_SIGN=1
bash "$SCRIPT_DIR/d1_record_local_drill.sh"
LOCAL="$(ls -1t "$ROOT/packages/aiplat-fde/docs/drills"/local-fde-field-local-*.json | head -1)"
cp "$LOCAL" "$EVID_DIR/$(basename "$LOCAL")"
rm -f "$ITEMS"

{
  echo "# FDE Field D1 Local Regression Runlog"
  echo ""
  echo "- recorded_at: \`$STAMP\`"
  echo "- environment: \`local\`"
  echo "- demo_root: \`$DEMO_ROOT\`"
  echo "- result: **PASS**"
  echo "- INSTALL_META: present (\`production_field=true\`)"
  echo "- production_signed: **false**"
  echo "- evidence: \`ops/evidence/$(basename "$LOCAL")\`"
  echo ""
  echo "Re-run: \`bash packages/aiplat-fde/scripts/d1_local_regression.sh\`"
} >"$RUNLOG"

pass "FDE Field D1 local regression — $RUNLOG"
