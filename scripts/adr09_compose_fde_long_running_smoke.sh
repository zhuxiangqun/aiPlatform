#!/usr/bin/env bash
# F11 / ADR-FDE-COMPOSE-LONG-RUNNING — FDE optional compose long-running smoke.
# up -d → curl /health → down -v. Always cleans up (no lingering CI containers).
# NOT forced production default. ≠ Field pack (ADR-DRAFT-fde-field-compose).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$REPO/packages/aiplat-fde"
COMPOSE_FILE="$RUNTIME/compose.fde-long-running.yml"
REPORT_DIR="${ADR09_FDE_COMPOSE_LR_SMOKE_REPORT_DIR:-/tmp/aiplat-adr09-fde-compose-lr-smoke}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPORT_DIR/run-$STAMP.txt"
PORT="${ADR09_FDE_HEALTH_PORT:-18766}"
UP=0

cleanup() {
  if [[ "$UP" -eq 1 ]]; then
    (cd "$RUNTIME" && docker compose -f compose.fde-long-running.yml down -v) || true
  fi
}
trap cleanup EXIT

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: FDE compose long-running smoke refuses AIPLAT_ENTERPRISE=1" >&2
  exit 3
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: missing $COMPOSE_FILE" >&2
  exit 4
fi

{
  echo "F11 FDE compose long-running smoke ts=$STAMP"
  echo "NOTE: optional profile; always down -v; not forced prod default; signoff stays on control plane"

  echo "== docker compose config =="
  (cd "$RUNTIME" && docker compose -f compose.fde-long-running.yml config) >/dev/null

  echo "== up -d =="
  (cd "$RUNTIME" && docker compose -f compose.fde-long-running.yml up -d)
  UP=1

  echo "== wait health port=$PORT =="
  ok=0
  for _ in $(seq 1 45); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/tmp/aiplat-fde-compose-lr-health.json 2>/dev/null; then
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "ERROR: health not ready" >&2
    (cd "$RUNTIME" && docker compose -f compose.fde-long-running.yml logs) || true
    exit 5
  fi
  cat /tmp/aiplat-fde-compose-lr-health.json
  echo
  echo "$ok" >/dev/null
  grep -q '"ok": true' /tmp/aiplat-fde-compose-lr-health.json
  grep -q '"product": "fde"' /tmp/aiplat-fde-compose-lr-health.json
  echo "PASS: health ok"

  echo "== down -v =="
  (cd "$RUNTIME" && docker compose -f compose.fde-long-running.yml down -v)
  UP=0
  echo "PASS: F11 compose smoke complete (containers removed)"
  echo "ROLLBACK: down -v (already run); prefer one-shot host phase_health"
  echo "REPORT_LOG=$LOG"
} | tee "$LOG"
