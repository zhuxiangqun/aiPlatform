#!/usr/bin/env bash
# ADR-09 step4 BOUNDARY B — isolated diagnosis-mvp AIPLAT_HOME (one-shot).
# ADR10_DIAGNOSIS_MVP_SPLIT=1; default home /tmp/aiplat-diagnosis-mvp
#   or $HOME/.aiplat/diagnosis-mvp with ADR10_ALLOW_USER_HOME=1.
# Does NOT authorize compose long-running / other four products.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR10_PHASE_SPLIT_REPORT_DIR:-/tmp/aiplat-adr10-phase-split}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: phase_split refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

{
  echo "ADR-10/ADR-09 BOUNDARY B split-home ts=$STAMP"
  echo "NOTE: one-shot only; not compose long-running; product=diagnosis MVP"

  echo "== SPLIT=1 sandbox home (/tmp/aiplat-diagnosis-mvp) =="
  unset ADR10_DIAG_AIPLAT_HOME || true
  ADR10_DIAGNOSIS_MVP_SPLIT=1 \
    AIPLAT_DIAGNOSIS_PROD_DEFAULT=0 \
    ADR10_ALLOW_USER_HOME=0 \
    bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  echo "PASS: SPLIT sandbox home"

  if [[ "${ADR10_PHASE_SPLIT_SKIP_USER_HOME:-0}" != "1" ]]; then
    echo "== SPLIT=1 user home (\$HOME/.aiplat/diagnosis-mvp) =="
    unset ADR10_DIAG_AIPLAT_HOME || true
    ADR10_DIAGNOSIS_MVP_SPLIT=1 \
      AIPLAT_DIAGNOSIS_PROD_DEFAULT=0 \
      ADR10_ALLOW_USER_HOME=1 \
      bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
    echo "PASS: SPLIT user home"
  else
    echo "SKIP: user-home pass (ADR10_PHASE_SPLIT_SKIP_USER_HOME=1)"
  fi

  echo "PASS: BOUNDARY B complete"
  echo "ROLLBACK: unset ADR10_DIAGNOSIS_MVP_SPLIT; optional rm -rf /tmp/aiplat-diagnosis-mvp \$HOME/.aiplat/diagnosis-mvp"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
