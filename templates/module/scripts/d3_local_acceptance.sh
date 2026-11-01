#!/usr/bin/env bash
# Template D3 local acceptance (UAT dry-run) — copy into packages/<capability>/scripts/.
# environment=local only. Never production_signed / authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# REPLACE_ME: AIPLAT_*_PREFIX + demo root
DEMO_ROOT="${AIPLAT_EXAMPLE_D3_DEMO_ROOT:-/tmp/aiplat-example-d3-uat-${STAMP}}"
export AIPLAT_HOME="$DEMO_ROOT/home"
export AIPLAT_EXAMPLE_PREFIX="$DEMO_ROOT/example"
mkdir -p "$AIPLAT_HOME" "$AIPLAT_EXAMPLE_PREFIX"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== EXAMPLE D3 local acceptance (template; not production) =="
[[ -x "$SCRIPT_DIR/d2_admin_check.sh" ]] && bash "$SCRIPT_DIR/d2_admin_check.sh"
bash "$SCRIPT_DIR/d1_install.sh" || fail "install"
bash "$SCRIPT_DIR/d1_upgrade.sh" || fail "upgrade"
bash "$SCRIPT_DIR/d1_rollback.sh" --runtime || fail "rollback"
[[ -x "$SCRIPT_DIR/d1_backup.sh" ]] && bash "$SCRIPT_DIR/d1_backup.sh"
pass "template d3_local_acceptance (customize before use)"
