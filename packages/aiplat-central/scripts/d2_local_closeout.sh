#!/usr/bin/env bash
# aiPlat Central D2 Thin local closeout — version/compat/security + N-1 + PG/HA local only.
# Never sets cutover_authorized=true. Never production_signed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_CENTRAL_D2_DEMO_ROOT:-/tmp/aiplat-central-d2-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_CENTRAL_PREFIX="$DEMO_ROOT/central"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_CENTRAL_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
CLOSEOUT="$ROOT/reports/five-products/ops/AIPLAT_D2_THIN_LOCAL_CLOSEOUT.md"
DRILL="$ROOT/packages/aiplat-central/docs/drills"
mkdir -p "$EVID" "$DRILL"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== aiPlat Central D2 Thin local closeout (does NOT authorize cutover) =="
echo "DEMO_ROOT=$DEMO_ROOT"

bash "$SCRIPT_DIR/a2_version_check.sh" || fail "a2_version_check"
bash "$SCRIPT_DIR/d2_compat_check.sh" || fail "d2_compat_check"
bash "$SCRIPT_DIR/d2_security_check.sh" || fail "d2_security_check"

# Sibling D2 packs (already in five_products_gate; re-assert file gate here)
bash "$ROOT/packages/aiplat-pi-runtime/scripts/d2_admin_check.sh" || fail "pi d2_admin"
bash "$ROOT/packages/aiplat-fde/scripts/d2_admin_check.sh" || fail "fde d2_admin"
bash "$ROOT/packages/aiplat-ontology/scripts/d2_admin_check.sh" || fail "ontology d2_admin"
bash "$ROOT/packages/aiplat-evaluation/scripts/d2_admin_check.sh" || fail "evaluation d2_admin"

bash "$SCRIPT_DIR/d1_install.sh" || fail "d1_install"
BEFORE="$(readlink "$AIPLAT_CENTRAL_PREFIX/current" 2>/dev/null || true)"
[[ -n "$BEFORE" ]] || fail "missing current after install"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "d1_upgrade"
AFTER="$(readlink "$AIPLAT_CENTRAL_PREFIX/current" 2>/dev/null || true)"
[[ -n "$AFTER" && "$AFTER" != "$BEFORE" ]] || fail "upgrade did not flip ($BEFORE → $AFTER)"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "d1_rollback --runtime"
ROLLED="$(readlink "$AIPLAT_CENTRAL_PREFIX/current" 2>/dev/null || true)"
[[ "$ROLLED" == "$BEFORE" ]] || fail "runtime rollback mismatch"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "d1_backup"

# PG/HA local only (sqlite / optional docker) — never authorize
bash "$SCRIPT_DIR/pg_ha_local_rehearsal.sh" || fail "pg_ha_local_rehearsal"
bash "$SCRIPT_DIR/pg_ha_prep_check.sh" || fail "pg_ha_prep_check"
if bash "$SCRIPT_DIR/pg_ha_cutover_authorize.sh" authorize; then
  fail "cutover authorize must REFUSE"
fi
pass "cutover authorize REFUSED"

python3 "$ROOT/scripts/check_five_products_status_sync.py" || fail "STATUS sync"
python3 "$ROOT/reports/five-products/modules/aiplat/contracts/validate_sample.py" || fail "aiplat contracts"

OUT="$DRILL/local-aiplat-d2-thin-local-${STAMP}.json"
python3 - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "aiplat_central_d2_thin_local_closeout",
  "at": "$STAMP",
  "environment": "local",
  "delivery": "D2_thin",
  "before_current": "$BEFORE",
  "after_upgrade": "$AFTER",
  "after_runtime_rollback": "$ROLLED",
  "compat_check": True,
  "security_check": True,
  "a2_version_check": True,
  "pg_ha_local_rehearsal": True,
  "cutover_authorized": False,
  "production_signed": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"

cat >"$CLOSEOUT" <<EOF
# aiPlat Central D2 Thin Local Closeout

- recorded_at: \`$STAMP\`
- environment: \`local\` (Option B)
- result: **PASS**
- \`cutover_authorized\`: **false**
- evidence: \`ops/evidence/$(basename "$OUT")\`

## Covered

| Item | Result |
|------|--------|
| A2 version SSOT | PASS |
| D2 compat matrix | PASS |
| D2+ security baseline | PASS |
| Sibling D2 packs (Pi/FDE/Onto/Eval) | PASS |
| Install → upgrade → runtime rollback → backup | PASS |
| PG/HA local rehearsal + prep | PASS (local only) |
| Cutover authorize | **REFUSED** |

## Commands

\`\`\`bash
bash packages/aiplat-central/scripts/d2_local_closeout.sh
\`\`\`

## Non-claims

- Not staging_ready / production_signed  
- Not multi-tenant production HA  
- See [\`D2_THIN.md\`](../../packages/aiplat-central/docs/D2_THIN.md) · [\`LOCAL_DEFER.md\`](./LOCAL_DEFER.md)
EOF

pass "aiPlat D2 Thin local closeout → $CLOSEOUT"
