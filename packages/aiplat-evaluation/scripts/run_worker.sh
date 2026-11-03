#!/usr/bin/env bash
# B2-L: start eval worker loop (local only). Does NOT flip process_split_authorized.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AIPLAT_EVAL_MODE="${AIPLAT_EVAL_MODE:-standalone}"
export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
export AIPLAT_EVAL_WORKER_ID="${AIPLAT_EVAL_WORKER_ID:-worker-local}"
export AIPLAT_EVAL_WORKER_IDLE_SLEEP="${AIPLAT_EVAL_WORKER_IDLE_SLEEP:-0.5}"
# Optional finite run for smoke: MAX_JOBS / MAX_IDLE
# export AIPLAT_EVAL_WORKER_MAX_JOBS=10
# export AIPLAT_EVAL_WORKER_MAX_IDLE=3
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "${ROOT}/data"
bash "${ROOT}/scripts/migrate_local.sh" >/dev/null

echo "aiplat-evaluation B2-L worker"
echo "  db=${AIPLAT_EVAL_DB_URL}"
echo "  worker_id=${AIPLAT_EVAL_WORKER_ID}"
echo "  process_split_authorized=false"
echo "  environment=local"

exec python3 -m app.worker
