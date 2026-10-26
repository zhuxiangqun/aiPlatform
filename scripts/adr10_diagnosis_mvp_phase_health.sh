#!/usr/bin/env bash
# ADR-09 step4 BOUNDARY C — one-shot thin health HTTP for diagnosis MVP.
# Starts stdlib server, curls /health, kills process. NOT compose long-running.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR10_PHASE_HEALTH_REPORT_DIR:-/tmp/aiplat-adr10-phase-health}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
PORT="${ADR10_DIAG_HEALTH_PORT:-18765}"
HOME_DIR="${ADR10_DIAG_AIPLAT_HOME:-/tmp/aiplat-diagnosis-mvp}"
PY="${ADR10_DIAG_PYTHON:-python3}"
PID=""

cleanup() {
  if [[ -n "${PID}" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: phase_health refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

{
  echo "ADR-09 BOUNDARY C health one-shot ts=$STAMP"
  echo "NOTE: not compose long-running; product=diagnosis MVP"

  mkdir -p "$HOME_DIR"
  export AIPLAT_HOME="$HOME_DIR"
  export ADR10_DIAGNOSIS_MVP_SPLIT=1
  export ADR10_DIAG_HEALTH_PORT="$PORT"
  export ADR10_DIAG_HEALTH_HOST=127.0.0.1

  echo "== start health server port=$PORT home=$HOME_DIR =="
  "$PY" "$REPO/scripts/adr10_diagnosis_mvp_health_server.py" &
  PID=$!
  sleep 0.4
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ERROR: health server failed to start" >&2
    exit 5
  fi

  echo "== curl /health =="
  out="$(curl -sf "http://127.0.0.1:${PORT}/health")"
  echo "$out"
  echo "$out" | grep -q '"ok": true'
  echo "$out" | grep -q 'diagnosis-mvp'
  echo "PASS: health JSON ok"

  cleanup
  PID=""
  echo "PASS: BOUNDARY C complete (server stopped)"
  echo "ROLLBACK: none beyond process exit; unset ADR10_DIAG_HEALTH_PORT"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
