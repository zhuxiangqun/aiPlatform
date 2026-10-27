#!/usr/bin/env bash
# ADR-09 compose long-running BOUNDARY C — Pi Thin profile smoke.
# up -d → curl /health → down -v. Always cleans up (no lingering CI containers).
# Authorize: ADR09_COMPOSE_LONG_RUNNING_DECISION.md. NOT forced production default.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$REPO/packages/aiplat-pi-runtime"
COMPOSE_FILE="$RUNTIME/compose.pi-thin-long-running.yml"
REPORT_DIR="${ADR09_COMPOSE_LR_SMOKE_REPORT_DIR:-/tmp/aiplat-adr09-compose-lr-smoke}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
PORT="${ADR09_COMPOSE_LR_PORT:-18787}"
UP=0

cleanup() {
  if [[ "$UP" -eq 1 ]]; then
    (cd "$RUNTIME" && docker compose -f compose.pi-thin-long-running.yml down -v) || true
  fi
}
trap cleanup EXIT

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: compose long-running smoke refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: missing $COMPOSE_FILE" >&2
  exit 4
fi

{
  echo "ADR-09 compose long-running BOUNDARY C smoke ts=$STAMP"
  echo "NOTE: optional profile; always down -v; not forced prod default"

  echo "== docker compose config =="
  (cd "$RUNTIME" && docker compose -f compose.pi-thin-long-running.yml config) >/dev/null

  echo "== up -d =="
  (cd "$RUNTIME" && docker compose -f compose.pi-thin-long-running.yml up -d)
  UP=1

  echo "== wait health port=$PORT =="
  ok=0
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/tmp/aiplat-compose-lr-health.json 2>/dev/null; then
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "ERROR: health not ready" >&2
    (cd "$RUNTIME" && docker compose -f compose.pi-thin-long-running.yml logs) || true
    exit 5
  fi
  cat /tmp/aiplat-compose-lr-health.json
  echo
  echo "PASS: health ok"

  echo "== down -v =="
  (cd "$RUNTIME" && docker compose -f compose.pi-thin-long-running.yml down -v)
  UP=0
  echo "PASS: BOUNDARY C complete (containers removed)"
  echo "ROLLBACK: down -v (already run); prefer one-shot / host pilot"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
