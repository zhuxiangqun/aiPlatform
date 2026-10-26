#!/usr/bin/env bash
# ADR-10 Phase D — D1 shared-home opt-in and/or D2 signoff default binding.
# ADR10_PHASE=d1 (default) | d2 | all
# Does NOT authorize E4 / ADR-09 / compose long-running.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${ADR10_PHASE:-d1}"
REPORT_DIR="${ADR10_PHASE_D_REPORT_DIR:-/tmp/aiplat-adr10-phase-d}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
D1_HOME="${ADR10_DIAG_AIPLAT_HOME:-$HOME/.aiplat/adr10-diagnosis-mvp-d1}"

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Phase D refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

run_d1() {
  echo "ADR-10 Phase D D1 shared-home ts=$STAMP"
  echo "NOTE: D1 shared-home; not E4; not ADR-09 Accepted"
  echo "D1_HOME=$D1_HOME"

  echo "== guard: bare PROD_DEFAULT=1 still refused =="
  set +e
  AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  rc=$?
  set -e
  if [[ "$rc" -ne 3 ]]; then
    echo "ERROR: expected exit 3 without ALLOW_USER_HOME, got $rc" >&2
    exit 5
  fi
  echo "PASS: bare PROD_DEFAULT=1 → exit 3"

  echo "== D1 smoke =="
  AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 \
    ADR10_ALLOW_USER_HOME=1 \
    ADR10_DIAG_AIPLAT_HOME="$D1_HOME" \
    bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"

  echo "PASS: ADR-10 Phase D D1 complete"
  echo "ROLLBACK: unset AIPLAT_DIAGNOSIS_PROD_DEFAULT ADR10_ALLOW_USER_HOME; optional rm -rf $D1_HOME"
}

run_d2() {
  local D2_HOME="${ADR10_DIAG_AIPLAT_HOME:-/tmp/aiplat-adr10-diag-home-d2-$STAMP}"
  mkdir -p "$D2_HOME"
  export PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"
  export AIPLAT_HOME="$D2_HOME"

  echo "ADR-10 Phase D2 signoff-default ts=$STAMP"
  echo "NOTE: unique entry=POST .../fde/acceptance/signoff via validate_slice_signoff_reports"
  echo "NOTE: not E4; not ADR-09 Accepted; not compose long-running"
  echo "D2_HOME=$D2_HOME"

  echo "== PROD_DEFAULT=1 requires report on legacy spec =="
  AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 python3 - <<'PY'
import os
from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    validate_slice_signoff_reports,
)

assert os.environ.get("AIPLAT_DIAGNOSIS_PROD_DEFAULT") == "1"
bad = validate_slice_signoff_reports({"spec_id": "legacy-d2-customer"})
assert bad.get("ok") is False and bad.get("required") is True, bad
rep = build_slice_diagnosis_report(
    scenario_id="legacy-d2-customer",
    run_id="d2-smoke",
    bundle_version="b",
    events=[{}],
)
good = validate_slice_signoff_reports(
    {"spec_id": "legacy-d2-customer", "evidence_report_ids": [rep["report_id"]]}
)
assert good.get("ok") is True, good
print("PASS: PROD_DEFAULT=1 binding")
PY

  echo "== rollback PROD_DEFAULT=0 =="
  AIPLAT_DIAGNOSIS_PROD_DEFAULT=0 python3 - <<'PY'
from core.apps.fde.service.slice_evidence import validate_slice_signoff_reports

r = validate_slice_signoff_reports({"spec_id": "legacy-d2-customer"})
assert r.get("ok") is True and r.get("required") is False, r
print("PASS: PROD_DEFAULT=0 rollback")
PY

  echo "PASS: ADR-10 Phase D2 complete"
  echo "ROLLBACK: export AIPLAT_DIAGNOSIS_PROD_DEFAULT=0"
}

{
  case "$PHASE" in
    d1) run_d1 ;;
    d2) run_d2 ;;
    all) run_d1; run_d2 ;;
    *)
      echo "ERROR: ADR10_PHASE must be d1|d2|all, got: $PHASE" >&2
      exit 2
      ;;
  esac
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
