#!/usr/bin/env bash
# ADR-09 preflight #5 — clean-env check scaffold (NOT E4 publicity approval).
# Runs isolated pilots; refuses AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 and AIPLAT_ENTERPRISE=1.
# Does not claim ADR-09 Accepted or external E4.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR09_E4_REPORT_DIR:-/tmp/aiplat-adr09-e4-clean-env}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"

{
  echo "ADR-09 E4 clean-env check (draft evidence) ts=$STAMP"
  echo "NOTE: not publicity approval; ADR-09 remains Proposed"
  if [[ "${AIPLAT_DIAGNOSIS_PROD_DEFAULT:-0}" == "1" ]]; then
    echo "ERROR: refuse AIPLAT_DIAGNOSIS_PROD_DEFAULT=1" >&2
    exit 3
  fi
  if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
    echo "ERROR: refuse AIPLAT_ENTERPRISE=1 in clean-env check" >&2
    exit 3
  fi
  echo "== ADR-10 diagnosis MVP host pilot =="
  bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  echo "== Gate3 Pi Thin phase=a (stub) =="
  GATE3_PI_THIN_PHASE=a bash "$REPO/packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh"
  echo "PASS: clean-env host checks (compose optional; skip if no daemon)"
  if docker info >/dev/null 2>&1; then
    echo "== ADR-10 compose one-shot =="
    docker compose -f "$REPO/compose.adr10-diagnosis-mvp.yml" run --rm adr10-diagnosis-mvp
    docker compose -f "$REPO/compose.adr10-diagnosis-mvp.yml" down -v || true
  else
    echo "SKIP: docker daemon unavailable"
  fi
  echo "PASS: adr09 clean-env scaffold complete"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
