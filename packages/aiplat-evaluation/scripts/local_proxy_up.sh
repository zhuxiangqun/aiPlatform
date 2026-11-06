#!/usr/bin/env bash
# Local-first: start eval standalone (:8010) + worker for Center job plane.
# Does NOT flip process_split_authorized. Opt-in via AIPLAT_EVAL_LOCAL_PROXY=1 (start.sh).
# Auth off by default so platform proxy can forward UI credentials without HS256 mint.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

# Prefer workspace .venv (has fastapi/uvicorn/PyJWT); bare python3 often lacks jwt.
PY="${AIPLAT_EVAL_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  else
    PY="$(command -v python3 || true)"
  fi
fi
if [[ -z "${PY:-}" ]]; then
  echo "ERROR: no python for eval local proxy" >&2
  exit 1
fi
if ! "$PY" -c 'import jwt, uvicorn' >/dev/null 2>&1; then
  echo "ERROR: $PY missing jwt/uvicorn — pip install 'PyJWT>=2.8' uvicorn (workspace .venv)" >&2
  exit 1
fi

EVAL_HOST="${AIPLAT_EVAL_HOST:-127.0.0.1}"
EVAL_PORT="${AIPLAT_EVAL_PORT:-8010}"
EVAL_URL="http://${EVAL_HOST}:${EVAL_PORT}"
DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
PID_DIR="${AIPLAT_EVAL_PID_DIR:-${AIPLAT_HOME:-$ROOT/../../.aiplat}/logs}"
mkdir -p "$PID_DIR" "${ROOT}/data"

export AIPLAT_EVAL_MODE="${AIPLAT_EVAL_MODE:-standalone}"
export AIPLAT_EVAL_HOST="$EVAL_HOST"
export AIPLAT_EVAL_PORT="$EVAL_PORT"
export AIPLAT_EVAL_DB_URL="$DB_URL"
export AIPLAT_EVAL_REQUIRE_AUTH="${AIPLAT_EVAL_REQUIRE_AUTH:-0}"
export AIPLAT_EVAL_JWT_SECRET="${AIPLAT_EVAL_JWT_SECRET:-aiplat-eval-local-dev-secret}"
export AIPLAT_EVAL_JWT_ISSUER="${AIPLAT_EVAL_JWT_ISSUER:-aiplat-eval-local}"
# local_stub: http_probe only; skill_suite needs docker (honest).
export AIPLAT_EVAL_SANDBOX_BACKEND="${AIPLAT_EVAL_SANDBOX_BACKEND:-local_stub}"
export AIPLAT_EVAL_SANDBOX_TIMEOUT="${AIPLAT_EVAL_SANDBOX_TIMEOUT:-30}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# First docker skill wrap can hang on image pull → pre-pull when docker backend.
if [[ "${AIPLAT_EVAL_SANDBOX_BACKEND}" == "docker" ]] && command -v docker >/dev/null 2>&1; then
  IMG="${AIPLAT_EVAL_SANDBOX_IMAGE:-alpine:3.20}"
  if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    echo "pre-pull sandbox image $IMG (first skill wrap)…"
    docker pull "$IMG" || echo "WARN: docker pull $IMG failed — skill_suite may timeout"
  fi
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -ti ":${EVAL_PORT}" >/dev/null 2>&1; then
    echo "WARN: port ${EVAL_PORT} already in use — skipping eval API start (healthz will be probed)"
  else
    bash "${ROOT}/scripts/migrate_local.sh" >/dev/null
    nohup "$PY" -m uvicorn app.main:app \
      --host "$EVAL_HOST" --port "$EVAL_PORT" --log-level info \
      > "${PID_DIR}/eval-api.log" 2>&1 &
    echo $! > "${PID_DIR}/eval-api.pid"
    echo "eval API PID=$(cat "${PID_DIR}/eval-api.pid") PY=$PY → ${EVAL_URL}"
  fi
else
  bash "${ROOT}/scripts/migrate_local.sh" >/dev/null
  nohup "$PY" -m uvicorn app.main:app \
    --host "$EVAL_HOST" --port "$EVAL_PORT" --log-level info \
    > "${PID_DIR}/eval-api.log" 2>&1 &
  echo $! > "${PID_DIR}/eval-api.pid"
  echo "eval API PID=$(cat "${PID_DIR}/eval-api.pid") PY=$PY → ${EVAL_URL}"
fi

ready=0
for i in $(seq 1 20); do
  if curl -fsS "${EVAL_URL}/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" != "1" ]]; then
  echo "ERROR: eval healthz not ready at ${EVAL_URL}" >&2
  tail -40 "${PID_DIR}/eval-api.log" 2>/dev/null || true
  exit 1
fi

# Worker shares DB with API
if [[ -f "${PID_DIR}/eval-worker.pid" ]] && kill -0 "$(cat "${PID_DIR}/eval-worker.pid")" 2>/dev/null; then
  echo "eval worker already running PID=$(cat "${PID_DIR}/eval-worker.pid")"
else
  nohup "$PY" -m app.worker \
    > "${PID_DIR}/eval-worker.log" 2>&1 &
  echo $! > "${PID_DIR}/eval-worker.pid"
  echo "eval worker PID=$(cat "${PID_DIR}/eval-worker.pid") PY=$PY"
fi

# Emit env hint for callers (start.sh sources via eval)
echo "AIPLAT_EVAL_SERVICE_URL=${EVAL_URL}"
echo "local_proxy_up OK · process_split_authorized=false · require_auth=${AIPLAT_EVAL_REQUIRE_AUTH}"
