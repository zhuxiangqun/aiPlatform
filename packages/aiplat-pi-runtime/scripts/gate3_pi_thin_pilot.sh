#!/usr/bin/env bash
# Gate3 Pi Thin pilot — smoke in an isolated env (ADR-08 / GATE3_PI_THIN_PILOT.md).
# Does not start platform/core control plane. Exits non-zero if AIPLAT_ENTERPRISE=1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${GATE3_PI_THIN_ENV:-$ROOT/.env.gate3-pi-thin}"
EXAMPLE="$SCRIPT_DIR/gate3_pi_thin.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    echo "NOTE: $ENV_FILE missing — loading example defaults from $EXAMPLE"
    ENV_FILE="$EXAMPLE"
  else
    echo "ERROR: missing $ENV_FILE and $EXAMPLE" >&2
    exit 2
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Gate3 Pi Thin pilot must not run with AIPLAT_ENTERPRISE=1 (control-plane bleed)." >&2
  exit 3
fi

export AIPLAT_HTTP_STUB="${AIPLAT_HTTP_STUB:-1}"
export AIPLAT_HTTP_PORT="${AIPLAT_HTTP_PORT:-18787}"
export AIPLAT_HTTP_API_KEY="${AIPLAT_HTTP_API_KEY:-gate3-pi-thin-pilot-key}"
if [[ -z "${AIPLAT_APP_HOME:-}" ]]; then
  export AIPLAT_APP_HOME="$ROOT/fixtures/sample-app"
fi

echo "Gate3 Pi Thin pilot: stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME enterprise=${AIPLAT_ENTERPRISE:-0}"
exec bash "$ROOT/scripts/http_smoke.sh"
