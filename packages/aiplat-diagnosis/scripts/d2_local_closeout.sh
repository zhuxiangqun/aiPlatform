#!/usr/bin/env bash
# Diagnosis D2 cohost local closeout. Never authorizes process_split.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEMO_ROOT="${AIPLAT_DIAGNOSIS_D2_DEMO_ROOT:-/tmp/aiplat-diagnosis-d2-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_DIAGNOSIS_PREFIX="$DEMO_ROOT/diagnosis"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_DIAGNOSIS_PREFIX"
EVID="$ROOT/reports/five-products/ops/evidence"
CLOSEOUT="$ROOT/reports/five-products/ops/DIAGNOSIS_D2_LOCAL_CLOSEOUT.md"
DRILL="$ROOT/packages/aiplat-diagnosis/docs/drills"
mkdir -p "$EVID" "$DRILL"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Diagnosis D2 local closeout (cohost; does NOT authorize) =="
bash "$SCRIPT_DIR/d2_admin_check.sh" || fail "d2_admin_check"

t0=$(date +%s)
python3 "$ROOT/reports/five-products/modules/diagnosis/contracts/validate_sample.py" || fail "validate_sample"
t1=$(date +%s)
PERF=$((t1 - t0))
[[ "$PERF" -lt 5 ]] || fail "contract sample took ${PERF}s (>=5)"

bash "$SCRIPT_DIR/d1_install.sh" || fail "d1_install"
BEFORE="$(readlink "$AIPLAT_DIAGNOSIS_PREFIX/current" 2>/dev/null || true)"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "d1_upgrade"
AFTER="$(readlink "$AIPLAT_DIAGNOSIS_PREFIX/current" 2>/dev/null || true)"
[[ -n "$AFTER" && "$AFTER" != "$BEFORE" ]] || fail "upgrade did not flip"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "d1_rollback --runtime"
ROLLED="$(readlink "$AIPLAT_DIAGNOSIS_PREFIX/current" 2>/dev/null || true)"
[[ "$ROLLED" == "$BEFORE" ]] || fail "runtime rollback mismatch"
if [[ "${AIPLAT_D2_INCLUDE_SMOKE:-0}" == "1" ]]; then
  bash "$SCRIPT_DIR/d1_smoke.sh" || fail "d1_smoke"
fi
bash "$SCRIPT_DIR/a3_local_rehearsal.sh" || fail "a3_local_rehearsal"
bash "$ROOT/packages/aiplat-central/scripts/d2_compat_check.sh" || fail "compat"

if bash "$SCRIPT_DIR/a3_split_authorize.sh" authorize; then
  fail "a3_split_authorize must REFUSE"
fi
pass "a3_split_authorize REFUSED"

OUT="$DRILL/local-diagnosis-d2-local-${STAMP}.json"
python3 - <<PY
import json
from pathlib import Path
Path(r"""$OUT""").write_text(json.dumps({
  "kind": "diagnosis_d2_cohost_local_closeout",
  "at": "$STAMP",
  "environment": "local",
  "delivery_mode": "cohost",
  "delivery_alias": "D1c",
  "perf_contract_seconds": $PERF,
  "before_current": "$BEFORE",
  "after_upgrade": "$AFTER",
  "after_runtime_rollback": "$ROLLED",
  "process_split_authorized": False,
  "production_signed": False,
}, indent=2) + "\n")
print("OK wrote", r"""$OUT""")
PY
cp "$OUT" "$EVID/$(basename "$OUT")"

cat >"$CLOSEOUT" <<EOF
# Diagnosis D2 Local Closeout (cohost / D1c)

- recorded_at: \`$STAMP\`
- result: **PASS**
- \`process_split_authorized\`: **false**
- evidence: \`ops/evidence/$(basename "$OUT")\`
- contract sample: \`${PERF}s\` (<5)

Re-run: \`bash packages/aiplat-diagnosis/scripts/d2_local_closeout.sh\`
EOF
pass "Diagnosis D2 local closeout → $CLOSEOUT"
