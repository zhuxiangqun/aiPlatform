#!/usr/bin/env bash
# Pi D1 local regression (path B / C under PG/HA defer) — no staging, no authorize.
# Hermetic prefix under /tmp; install → smoke → backup → upgrade → runtime rollback →
# bundle rollback → Gate3 phase a/b/c.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# Always hermetic unless operator pins AIPLAT_PI_D1_DEMO_ROOT (ignore ambient AIPLAT_PI_PREFIX).
DEMO_ROOT="${AIPLAT_PI_D1_DEMO_ROOT:-/tmp/aiplat-pi-d1-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_PI_PREFIX="$DEMO_ROOT/pi"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_PI_PREFIX"

RUNLOG="${AIPLAT_PI_D1_RUNLOG:-$REPO/reports/five-products/ops/PI_D1_LOCAL_REGRESSION.md}"
mkdir -p "$(dirname "$RUNLOG")"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== Pi D1 local regression (environment=local; does not authorize) =="
echo "DEMO_ROOT=$DEMO_ROOT"

bash packages/aiplat-pi-runtime/scripts/d1_install.sh --smoke || fail "d1_install --smoke"
bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh || fail "d1_smoke"
bash packages/aiplat-pi-runtime/scripts/d1_backup.sh || fail "d1_backup"
bash packages/aiplat-pi-runtime/scripts/d1_upgrade.sh || fail "d1_upgrade"
CUR_AFTER_UP="$(readlink "$AIPLAT_PI_PREFIX/current" || true)"
bash packages/aiplat-pi-runtime/scripts/d1_rollback.sh --runtime || fail "d1_rollback --runtime"
CUR_AFTER_RT="$(readlink "$AIPLAT_PI_PREFIX/current" || true)"
[[ -n "$CUR_AFTER_UP" && -n "$CUR_AFTER_RT" && "$CUR_AFTER_UP" != "$CUR_AFTER_RT" ]] \
  || fail "runtime rollback did not flip current ($CUR_AFTER_UP → $CUR_AFTER_RT)"
bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh || fail "smoke after runtime rollback"

PREV_BUNDLE="${DEMO_ROOT}/prev-bundle"
rm -rf "$PREV_BUNDLE"
mkdir -p "$PREV_BUNDLE"
cp -R packages/aiplat-pi-runtime/fixtures/sample-app/. "$PREV_BUNDLE/"
echo '{"marker":"d1-prev"}' >"$PREV_BUNDLE/.d1_prev_marker.json"
bash packages/aiplat-pi-runtime/scripts/d1_rollback.sh --bundle "$PREV_BUNDLE" || fail "bundle rollback"
[[ -f "$AIPLAT_PI_PREFIX/bundles/current/.d1_prev_marker.json" ]] || fail "bundle marker missing"
bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh || fail "smoke after bundle rollback"

GATE3_PI_THIN_PHASE=a bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh || fail "gate3 phase a"
GATE3_PI_THIN_PHASE=b bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh || fail "gate3 phase b"
GATE3_PI_THIN_PHASE=c bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh || fail "gate3 phase c"

{
  echo "# Pi D1 Local Regression Runlog"
  echo ""
  echo "- recorded_at: \`$STAMP\`"
  echo "- environment: \`local\` (not staging; **no** production_signed / authorize)"
  echo "- demo_root: \`$DEMO_ROOT\`"
  echo "- operator: \`${USER:-ops}\`"
  echo "- result: **PASS**"
  echo "- d3_production_authorized: **false** (unchanged)"
  echo "- cutover_authorized: **false** (unchanged)"
  echo ""
  echo "## Steps"
  echo ""
  echo "| Step | Result |"
  echo "|------|--------|"
  echo "| d1_install --smoke | PASS |"
  echo "| d1_smoke | PASS |"
  echo "| d1_backup | PASS |"
  echo "| d1_upgrade (distinct slot) | PASS (\`$CUR_AFTER_UP\`) |"
  echo "| d1_rollback --runtime | PASS (\`$CUR_AFTER_RT\`) |"
  echo "| d1_rollback --bundle | PASS |"
  echo "| Gate3 phase a/b/c | PASS |"
  echo ""
  echo "## Notes"
  echo ""
  echo "- Same package.json version re-upgrade uses \`version+UTC\` slot so runtime rollback flips."
  echo "- PG/HA / A3 / D3 live authorize remain deferred (\`staging_ready=false\`)."
  echo ""
  echo "See [\`LOCAL_DEFER.md\`](./LOCAL_DEFER.md) · [\`../GATE3_PI_THIN_ROLLBACK_DRILL.md\`](../GATE3_PI_THIN_ROLLBACK_DRILL.md)."
} >"$RUNLOG"

pass "Pi D1 local regression — runlog $RUNLOG"
