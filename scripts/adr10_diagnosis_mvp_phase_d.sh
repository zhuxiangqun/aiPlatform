#!/usr/bin/env bash
# ADR-10 Phase D — D1 shared-home opt-in (NOT D2 platform default binding).
# Requires explicit PROD_DEFAULT=1 + ALLOW_USER_HOME=1; home under $HOME.
# Does NOT authorize E4 / ADR-09 / platform route defaults.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR10_PHASE_D_REPORT_DIR:-/tmp/aiplat-adr10-phase-d}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
D1_HOME="${ADR10_DIAG_AIPLAT_HOME:-$HOME/.aiplat/adr10-diagnosis-mvp-d1}"

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Phase D refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

{
  echo "ADR-10 Phase D D1 shared-home ts=$STAMP"
  echo "NOTE: D1 only; not D2; not E4; not ADR-09 Accepted"
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
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
