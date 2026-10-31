#!/usr/bin/env bash
# Pi D1 smoke — stub HTTP + /healthz contract + legacy /health.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_node
PKG="$(d1_repo_pkg)"
PREFIX="$(d1_prefix)"

# Prefer installed current if present; else repo tree
HTTP_BIN="$PKG/bin/aiplat-http.mjs"
APP_HOME="$PKG/fixtures/sample-app"
API_KEY="pi-d1-smoke-key"
if [[ -x "$PREFIX/bin/aiplat-http" && -f "$PREFIX/env" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$PREFIX/env"; set +a
  HTTP_BIN="$PREFIX/current/bin/aiplat-http.mjs"
  APP_HOME="${AIPLAT_APP_HOME:-$APP_HOME}"
  API_KEY="${AIPLAT_HTTP_API_KEY:-$API_KEY}"
fi

# Always bind an ephemeral port for smoke (ignore env AIPLAT_HTTP_PORT)
PORT="${AIPLAT_PI_SMOKE_PORT:-$((29000 + RANDOM % 1000))}"
export AIPLAT_HTTP_PORT="$PORT"
export AIPLAT_HTTP_STUB=1
export AIPLAT_APP_HOME="$APP_HOME"
export AIPLAT_HTTP_API_KEY="$API_KEY"
export AIPLAT_ENTERPRISE=0

node "$HTTP_BIN" &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then break; fi
  sleep 0.1
done

HEALTHZ="$(curl -fsS "http://127.0.0.1:$PORT/healthz")"
echo "$HEALTHZ" | grep -q '"status":"ok"'
echo "$HEALTHZ" | grep -q '"product_id":"pi"'

# Schema check (zero-dep)
echo "$HEALTHZ" | python3 -c '
import json, sys
obj = json.load(sys.stdin)
assert obj.get("status") == "ok", obj
assert obj.get("product_id") == "pi", obj
assert "version" in obj, obj
print("OK healthz contract")
'

curl -fsS "http://127.0.0.1:$PORT/health" | grep -q '"ok":true'

echo "PASS: Pi D1 smoke (healthz + health) port=$PORT"
