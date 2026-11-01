#!/usr/bin/env bash
# Pi D3 local engineering closeout (Option B / environment=local).
# Never flips checklist 🟨→✅. Never sets d3_production_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$ROOT/reports/five-products/ops/evidence"
CLOSEOUT="$ROOT/reports/five-products/ops/PI_D3_LOCAL_CLOSEOUT.md"
DRILL="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$EVID" "$DRILL"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Pi D3 local closeout (does NOT authorize) =="
echo "stamp=$STAMP"

bash "$SCRIPT_DIR/d2_admin_check.sh" || fail "d2_admin_check"
bash "$SCRIPT_DIR/d3_local_rehearsal.sh" || fail "d3_local_rehearsal"
bash "$SCRIPT_DIR/d3_soc_local_rehearsal.sh" || fail "d3_soc_local_rehearsal"
bash "$SCRIPT_DIR/d3_n1_local_rehearsal.sh" || fail "d3_n1_local_rehearsal"
bash "$SCRIPT_DIR/d3_prep_check.sh" || fail "d3_prep_check"

bash "$SCRIPT_DIR/d3_authorize.sh" status >/dev/null || true
if bash "$SCRIPT_DIR/d3_authorize.sh" authorize; then
  fail "d3_authorize must REFUSE while checklist has 🟨"
fi
pass "d3_authorize REFUSED (expected)"

# Copy latest drills into ops/evidence
for pat in local-rehearsal-*.json soc-rehearsal-*.json n1-rehearsal-*.json local-pi-d3-local-*.json; do
  f="$(ls -1t "$DRILL"/$pat 2>/dev/null | head -1 || true)"
  [[ -n "$f" ]] || continue
  cp "$f" "$EVID/$(basename "$f")"
done

LOCAL_REH="$(ls -1t "$DRILL"/local-rehearsal-*.json | head -1)"
SOC_REH="$(ls -1t "$DRILL"/soc-rehearsal-*.json | head -1)"
N1_REH="$(ls -1t "$DRILL"/n1-rehearsal-*.json | head -1)"

cat >"$CLOSEOUT" <<EOF
# Pi D3 Local Closeout

- recorded_at: \`$STAMP\`
- environment: \`local\` (Option B · not staging)
- result: **PASS** (engineering local only)
- \`d3_production_authorized\`: **false**
- \`production_signed\`: **false**
- checklist #3/#4/#5/#6: **🟨** (not ✅)

## Commands

\`\`\`bash
bash packages/aiplat-pi-runtime/scripts/d3_local_closeout.sh
\`\`\`

## Evidence

| Item | File |
|------|------|
| Bundle checksum + pointer rollback | \`$(basename "$LOCAL_REH")\` |
| SOC file-sink (enterprise opt-in) | \`$(basename "$SOC_REH")\` |
| N-1 install/upgrade/runtime rollback | \`$(basename "$N1_REH")\` |
| Prep status | \`packages/aiplat-pi-runtime/docs/d3/PREP_STATUS.json\` |
| Checklist | \`packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md\` |

## Local vs production

| Local (this closeout) | Still required for authorize |
|-----------------------|------------------------------|
| #3 checksum roundtrip | production / staging live signoff |
| #4 OPS_SURFACE docs | production ops SLA evidence |
| #5 file-sink SOC | real SOC outbound |
| #6 N-1 under hermetic prefix | staging/prod-canary N-1 live |

See [\`LIVE_DRILL_EVIDENCE.md\`](../../packages/aiplat-pi-runtime/docs/d3/LIVE_DRILL_EVIDENCE.md) · [\`LOCAL_DEFER.md\`](./LOCAL_DEFER.md).
EOF

pass "pi d3_local_closeout → $CLOSEOUT"
echo "NOTE: do not flip 🟨→✅; do not authorize"
