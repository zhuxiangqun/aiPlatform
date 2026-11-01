#!/usr/bin/env bash
# A1: start evaluation standalone on :8010 (local only).
# Does NOT flip process_split_authorized.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AIPLAT_EVAL_MODE="${AIPLAT_EVAL_MODE:-standalone}"
export AIPLAT_EVAL_HOST="${AIPLAT_EVAL_HOST:-127.0.0.1}"
export AIPLAT_EVAL_PORT="${AIPLAT_EVAL_PORT:-8010}"
export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "${ROOT}/data"

echo "aiplat-evaluation A1 local"
echo "  mode=${AIPLAT_EVAL_MODE}  http://${AIPLAT_EVAL_HOST}:${AIPLAT_EVAL_PORT}"
echo "  process_split_authorized=false"
echo "  healthz: curl -fsS http://${AIPLAT_EVAL_HOST}:${AIPLAT_EVAL_PORT}/healthz"

exec python3 -m uvicorn app.main:app \
  --host "${AIPLAT_EVAL_HOST}" \
  --port "${AIPLAT_EVAL_PORT}" \
  --log-level info
