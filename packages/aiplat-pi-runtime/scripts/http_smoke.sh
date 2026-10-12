#!/usr/bin/env bash
# Phase 2 HTTP smoke (stub mode — no LLM keys required)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${AIPLAT_HTTP_PORT:-$((28000 + RANDOM % 1000))}"
export AIPLAT_HTTP_PORT="$PORT"
export AIPLAT_HTTP_STUB=1
export AIPLAT_APP_HOME="${AIPLAT_APP_HOME:-$ROOT/fixtures/sample-app}"
export AIPLAT_HTTP_API_KEY="${AIPLAT_HTTP_API_KEY:-smoke-key}"

node "$ROOT/bin/aiplat-http.mjs" &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.15
done

AUTH=(-H "Authorization: Bearer $AIPLAT_HTTP_API_KEY" -H "content-type: application/json")

curl -fsS "http://127.0.0.1:$PORT/health" | grep -q '"ok":true'

CHAT=$(curl -fsS "${AUTH[@]}" -d '{"session_id":"s1","message":"ping"}' \
  "http://127.0.0.1:$PORT/v1/chat")
echo "$CHAT" | grep -q 'sop_injected=true'
echo "$CHAT" | grep -q 'AIPLAT_SOP_INJECT_OK'

SK=$(curl -fsS "${AUTH[@]}" -d '{"session_id":"s1","params":{"n":1}}' \
  "http://127.0.0.1:$PORT/v1/skills/demo_skill")
echo "$SK" | grep -q 'AIPLAT_DEMO_HANDLER_OK'

echo "PASS: aiplat-http smoke (health + chat SOP + demo_skill handler)"
