#!/usr/bin/env bash
# ADR-09 FDE BOUNDARY C — one-shot thin health HTTP for optional FDE deploy probe.
# Starts stdlib server, curls /health, kills process. NOT compose long-running.
# Does NOT start a second acceptance/signoff server.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${ADR09_FDE_PHASE_HEALTH_REPORT_DIR:-/tmp/aiplat-adr09-fde-phase-health}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
PORT="${ADR09_FDE_HEALTH_PORT:-18766}"
HOME_DIR="${ADR09_FDE_AIPLAT_HOME:-/tmp/aiplat-fde-optional}"
PY="${ADR09_FDE_PYTHON:-python3}"
PID=""

cleanup() {
  if [[ -n "${PID}" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: fde phase_health refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

{
  echo "ADR-09 FDE BOUNDARY C health one-shot ts=$STAMP"
  echo "NOTE: not compose long-running; product=fde; signoff stays on control plane"

  mkdir -p "$HOME_DIR"
  export AIPLAT_HOME="$HOME_DIR"
  export AIPLAT_FDE_OPTIONAL_SPLIT=1
  export ADR09_FDE_HEALTH_PORT="$PORT"
  export ADR09_FDE_HEALTH_HOST=127.0.0.1

  echo "== start health server port=$PORT home=$HOME_DIR =="
  "$PY" "$REPO/scripts/adr09_fde_optional_health_server.py" &
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
  echo "$out" | grep -q '"product": "fde"'
  echo "PASS: health JSON ok"

  echo "== curl /healthz (V2 A1 contract) =="
  hz="$(curl -sf "http://127.0.0.1:${PORT}/healthz")"
  echo "$hz"
  echo "$hz" | grep -q '"status": "ok"'
  echo "$hz" | grep -q '"product_id": "fde"'
  echo "PASS: healthz contract ok"

  cleanup
  PID=""
  echo "PASS: FDE BOUNDARY C complete (server stopped)"
  echo "ROLLBACK: process exit; unset AIPLAT_FDE_OPTIONAL_SPLIT / ADR09_FDE_HEALTH_PORT"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
