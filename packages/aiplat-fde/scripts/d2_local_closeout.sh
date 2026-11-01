#!/usr/bin/env bash
# FDE Field D2 local closeout — admin pack + upgrade/N-1 + D1 backup/rollback.
# environment=local only. Never production_signed / authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_FDE_D2_DEMO_ROOT:-/tmp/aiplat-fde-d2-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_FDE_PREFIX="$DEMO_ROOT/fde"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_FDE_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
CLOSEOUT="$ROOT/reports/five-products/ops/FDE_FIELD_D2_LOCAL_CLOSEOUT.md"
DRILL="$ROOT/packages/aiplat-fde/docs/drills"
mkdir -p "$EVID" "$DRILL"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== FDE Field D2 local closeout (environment=local) =="
echo "DEMO_ROOT=$DEMO_ROOT"

bash "$SCRIPT_DIR/d2_admin_check.sh" || fail "d2_admin_check"
bash "$SCRIPT_DIR/d1_install.sh" --smoke || fail "d1_install --smoke"
[[ -f "$AIPLAT_FDE_PREFIX/INSTALL_META.json" ]] || fail "INSTALL_META missing"
BEFORE="$(readlink "$AIPLAT_FDE_PREFIX/current" 2>/dev/null || true)"
[[ -n "$BEFORE" ]] || fail "missing current"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "d1_upgrade"
AFTER="$(readlink "$AIPLAT_FDE_PREFIX/current" 2>/dev/null || true)"
[[ -n "$AFTER" && "$AFTER" != "$BEFORE" ]] || fail "upgrade did not flip ($BEFORE → $AFTER)"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "d1_rollback --runtime"
ROLLED="$(readlink "$AIPLAT_FDE_PREFIX/current" 2>/dev/null || true)"
[[ "$ROLLED" == "$BEFORE" ]] || fail "runtime rollback failed ($ROLLED != $BEFORE)"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke after runtime rollback"
bash "$SCRIPT_DIR/d1_backup.sh" || fail "d1_backup"
BACKUP_TGZ="$(ls -1t "$AIPLAT_FDE_PREFIX/backups"/*.tgz 2>/dev/null | head -1 || true)"
[[ -n "$BACKUP_TGZ" ]] || fail "no backup tgz"
echo "pre-backup-rollback" >"$AIPLAT_FDE_PREFIX/logs/d2-marker.txt"
bash "$SCRIPT_DIR/d1_rollback.sh" --backup "$BACKUP_TGZ" || fail "d1_rollback --backup"
bash "$SCRIPT_DIR/d1_smoke.sh" || fail "smoke after backup rollback"

# Central compat matrix still lists fde
bash "$ROOT/packages/aiplat-central/scripts/d2_compat_check.sh" || fail "central d2_compat_check"

OUT="$DRILL/local-fde-d2-local-${STAMP}.json"
python3 - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(
    json.dumps(
        {
            "kind": "fde_field_d2_local_closeout",
            "at": "$STAMP",
            "environment": "local",
            "demo_root": "$DEMO_ROOT",
            "before_current": "$BEFORE",
            "after_upgrade": "$AFTER",
            "after_runtime_rollback": "$ROLLED",
            "backup_rollback": True,
            "d2_admin_check": True,
            "compat_matrix": True,
            "production_signed": False,
            "production_field": True,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"

cat >"$CLOSEOUT" <<EOF
# FDE Field D2 Local Closeout

- recorded_at: \`$STAMP\`
- environment: \`local\` (Option B)
- result: **PASS**
- production_signed: **false**
- Field D1 ADR: **Accepted** (unchanged)
- evidence: \`ops/evidence/$(basename "$OUT")\`

## Covered

| Item | Result |
|------|--------|
| D2 admin/security baseline | PASS (\`d2_admin_check.sh\`) |
| Install + INSTALL_META | PASS |
| Upgrade → runtime rollback | PASS (\`$BEFORE\` ↔ \`$AFTER\`) |
| Backup → restore rollback | PASS |
| Central compat matrix (fde row) | PASS |
| Unique signoff path | documented |

## Commands

\`\`\`bash
bash packages/aiplat-fde/scripts/d2_local_closeout.sh
\`\`\`

## Non-claims

- Not compose long-running  
- Not PG/HA / authorize  
- \`current_delivery\` remains **D1** in manifest；本包为 **D2 Field ops pack**（与 Pi D2 admin 同级叙事）
EOF

pass "FDE Field D2 local closeout → $CLOSEOUT"
