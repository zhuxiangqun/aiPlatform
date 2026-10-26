#!/usr/bin/env bash
# ADR-10 Phase C — diagnosis single-product deepen (soak + rollback).
# Does NOT flip production defaults. Does NOT authorize E4 or ADR-09.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR10_PHASE_C_REPORT_DIR:-/tmp/aiplat-adr10-phase-c}"
GAP_SEC="${ADR10_PHASE_C_GAP_SEC:-30}"
REPEAT="${ADR10_PHASE_C_REPEAT:-2}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
COMPOSE="$REPO/compose.adr10-diagnosis-mvp.yml"

if [[ "${AIPLAT_DIAGNOSIS_PROD_DEFAULT:-0}" == "1" ]]; then
  echo "ERROR: Phase C refuses AIPLAT_DIAGNOSIS_PROD_DEFAULT=1" >&2
  exit 3
fi
if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Phase C refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

{
  echo "ADR-10 Phase C diagnosis deepen ts=$STAMP gap=${GAP_SEC}s repeat=$REPEAT"
  echo "NOTE: not prod-default switch; not E4; not ADR-09 Accepted"

  echo "== refuse prod default =="
  set +e
  AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  rc=$?
  set -e
  if [[ "$rc" -ne 3 ]]; then
    echo "ERROR: expected exit 3 for prod-default=1, got $rc" >&2
    exit 5
  fi
  echo "PASS: refuse AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 (exit 3)"

  echo "== host start (repeat=$REPEAT) =="
  for i in $(seq 1 "$REPEAT"); do
    echo "-- host pass $i/$REPEAT --"
    ADR10_DIAG_AIPLAT_HOME="/tmp/aiplat-adr10-diag-home-c-start-$i" \
      bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  done

  echo "== gap ${GAP_SEC}s =="
  sleep "$GAP_SEC"

  echo "== host close (repeat=$REPEAT) =="
  for i in $(seq 1 "$REPEAT"); do
    echo "-- host close $i/$REPEAT --"
    ADR10_DIAG_AIPLAT_HOME="/tmp/aiplat-adr10-diag-home-c-close-$i" \
      bash "$REPO/scripts/adr10_diagnosis_mvp_pilot.sh"
  done

  if docker info >/dev/null 2>&1; then
    echo "== compose one-shot + rollback =="
    docker compose -f "$COMPOSE" run --rm adr10-diagnosis-mvp
    docker compose -f "$COMPOSE" down -v
    echo "PASS: compose + down -v"
  else
    echo "SKIP: docker daemon unavailable (host dual-end still required)"
  fi

  echo "PASS: ADR-10 Phase C complete"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
