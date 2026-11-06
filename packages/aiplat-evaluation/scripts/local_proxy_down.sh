#!/usr/bin/env bash
# Stop eval API + worker started by local_proxy_up.sh (local-first).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="${AIPLAT_EVAL_PID_DIR:-${AIPLAT_HOME:-$ROOT/../../.aiplat}/logs}"
EVAL_PORT="${AIPLAT_EVAL_PORT:-8010}"

stop_pidfile() {
  local f="$1" name="$2"
  if [[ -f "$f" ]]; then
    local pid
    pid="$(cat "$f" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
      echo "stopped $name PID=$pid"
    fi
    rm -f "$f"
  fi
}

stop_pidfile "${PID_DIR}/eval-worker.pid" "eval-worker"
stop_pidfile "${PID_DIR}/eval-api.pid" "eval-api(:${EVAL_PORT})"

# Best-effort: only kill listeners that look like eval uvicorn on EVAL_PORT
if command -v lsof >/dev/null 2>&1; then
  for pid in $(lsof -ti ":${EVAL_PORT}" 2>/dev/null || true); do
    if ps -p "$pid" -o args= 2>/dev/null | grep -q "app.main:app\|aiplat-evaluation"; then
      kill "$pid" 2>/dev/null || true
      echo "stopped leftover eval listener PID=$pid on :${EVAL_PORT}"
    fi
  done
fi

echo "local_proxy_down done"
