#!/usr/bin/env bash
# Shared packaging surface — every capability package must keep D1/D2 file gates.
# Does NOT authorize cutover / process_split / d3_production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

require_files() {
  local pkg="$1"; shift
  local base="packages/$pkg"
  [[ -d "$base" ]] || fail "missing package dir $base"
  local f
  for f in "$@"; do
    [[ -e "$base/$f" ]] || fail "$pkg missing $f"
  done
  ok "$pkg surface ($# files)"
}

# Common D1 thin install surface
D1_COMMON=(
  scripts/d1_lib.sh
  scripts/d1_install.sh
  scripts/d1_upgrade.sh
  scripts/d1_rollback.sh
  scripts/d1_smoke.sh
  scripts/sbom-sign.stub.sh
  package.json
)

require_files aiplat-central \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/a2_version_check.sh \
  scripts/d2_compat_check.sh \
  scripts/d2_security_check.sh \
  scripts/d2_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/D2_THIN.md \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md \
  compat/matrix.yaml

require_files aiplat-pi-runtime \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/d1_local_regression.sh \
  scripts/d2_admin_check.sh \
  scripts/d3_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md

require_files aiplat-fde \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/d1_local_regression.sh \
  scripts/d2_admin_check.sh \
  scripts/d2_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md

require_files aiplat-ontology \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/d2_admin_check.sh \
  scripts/d2_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md

require_files aiplat-evaluation \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/d2_admin_check.sh \
  scripts/d2_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md

# Sixth capability (DIAGNOSIS_V1 C3) — same D1/D2 surface; still D1c/cohost
require_files aiplat-diagnosis \
  "${D1_COMMON[@]}" \
  scripts/d1_backup.sh \
  scripts/d2_admin_check.sh \
  scripts/d2_local_closeout.sh \
  scripts/d3_local_acceptance.sh \
  security/baseline.yaml \
  docs/PERF_BASELINE.md \
  docs/uat/UAT.md \
  docs/D2_COHOST.md \
  docs/SECURITY.md \
  chart/Chart.yaml

# Shared baseline checker + template stubs
[[ -f scripts/lib/aiplat_security_baseline.py ]] || fail "missing shared security baseline checker"
[[ -f scripts/check_five_products_perf_baseline.sh ]] || fail "missing perf baseline gate"
[[ -f scripts/ops_d3_local_acceptance_all.sh ]] || fail "missing D3 acceptance aggregator"
[[ -f scripts/ops_five_products_e2e_local.sh ]] || fail "missing cross-capability E2E"
[[ -f reports/five-products/ops/ENGINEERING_UNFREEZE_D3_E2E.md ]] || fail "missing D3/E2E unfreeze record"
[[ -f templates/module/scripts/d3_local_acceptance.sh ]] || fail "missing template d3_local_acceptance"
[[ -f templates/module/uat/UAT.md ]] || fail "missing template UAT.md"
[[ -f templates/module/PACKAGING_BASE.md ]] || fail "missing templates/module/PACKAGING_BASE.md"
[[ -f templates/module/docs/PERF_BASELINE.md ]] || fail "missing template PERF_BASELINE.md"
[[ -f templates/module/security/baseline.yaml ]] || fail "missing template security baseline"
[[ -f templates/module/scripts/d2_admin_check.sh ]] || fail "missing template d2_admin_check"

ok "five_products packaging surface"
