#!/usr/bin/env bash
# Full live gate: offline + stub HTTP + Ollama CLI + HTTP agent mode.
# Requires: pi CLI, Ollama (or AIPLAT_PI_BASE_URL OpenAI-compatible endpoint).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
MODEL="${AIPLAT_PI_MODEL:-ollama/qwen2.5:3b}"
SAMPLE="$ROOT/fixtures/sample-app"
EXPORT_DIR="${AIPLAT_LIVE_EXPORT:-$REPO/dist/aiplat-app-sample}"

echo "== 1) offline structural =="
python3 "$ROOT/scripts/phase0_offline_check.py"
node "$ROOT/scripts/phase0_verify.mjs" >/dev/null
node "$ROOT/scripts/phase0_mock_extension.mjs" >/dev/null
echo "PASS: offline"

echo "== 2) stub HTTP =="
bash "$ROOT/scripts/http_smoke.sh"
echo "PASS: stub HTTP"

echo "== 3) ensure Ollama models.json (CLI) =="
bash "$ROOT/scripts/ensure_ollama_models_json.sh"

if ! command -v pi >/dev/null 2>&1; then
  echo "FAIL: pi CLI not found"
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: curl not found"
  exit 1
fi

# Fail fast if Ollama (default) is down unless custom base URL
if [[ -z "${AIPLAT_PI_BASE_URL:-}" ]]; then
  if ! curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "FAIL: Ollama not reachable at :11434 (set AIPLAT_PI_BASE_URL for other endpoints)"
    exit 1
  fi
fi

echo "== 4) export sample + CLI print =="
python3 "$REPO/scripts/export_pi_bundle.py" --app-home "$SAMPLE" --out "$EXPORT_DIR" >/dev/null
export AIPLAT_APP_HOME="$EXPORT_DIR"
# Isolate from stub HTTP leftovers
unset AIPLAT_HTTP_STUB AIPLAT_HTTP_PORT AIPLAT_HTTP_API_KEY || true

expect_grep() {
  local label="$1" needle="$2" body="$3"
  if ! printf '%s\n' "$body" | grep -q -- "$needle"; then
    echo "FAIL: $label — expected /$needle/"
    echo "----- output -----"
    printf '%s\n' "$body" | tail -80
    echo "----- end -----"
    exit 1
  fi
}

CLI_OUT=$(pi -e "$EXPORT_DIR" -p --no-session --model "$MODEL" \
  "Reply with exactly the token AIPLAT_PI_OK and nothing else." 2>&1 || true)
expect_grep "CLI print" 'AIPLAT_PI_OK' "$CLI_OUT"
echo "PASS: CLI print AIPLAT_PI_OK"

SOP_OUT=$(pi -e "$EXPORT_DIR" -p --no-session --model "$MODEL" \
  "Confirm SOP injection: include the exact marker AIPLAT_SOP_INJECT_OK in your reply." 2>&1 || true)
expect_grep "CLI SOP" 'AIPLAT_SOP_INJECT_OK' "$SOP_OUT"
echo "PASS: CLI SOP marker"

STATUS_OUT=$(pi -e "$EXPORT_DIR" -p --no-session --model "$MODEL" "/aiplat-status" 2>&1 || true)
expect_grep "/aiplat-status" 'AIPLAT_STATUS_OK' "$STATUS_OUT"
echo "PASS: /aiplat-status print visibility"

echo "== 5) HTTP agent mode (createAgentSession) =="
PORT="${AIPLAT_HTTP_PORT:-$((29000 + RANDOM % 1000))}"
export AIPLAT_HTTP_PORT="$PORT"
export AIPLAT_HTTP_API_KEY="${AIPLAT_HTTP_API_KEY:-live-smoke-key}"
export AIPLAT_PI_MODEL="$MODEL"
unset AIPLAT_HTTP_STUB || true

node "$ROOT/bin/aiplat-http.mjs" &
HPID=$!
cleanup() { kill "$HPID" 2>/dev/null || true; wait "$HPID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -fsS -H "Authorization: Bearer $AIPLAT_HTTP_API_KEY" \
    "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

AUTH=(-H "Authorization: Bearer $AIPLAT_HTTP_API_KEY" -H "content-type: application/json")
CHAT=$(curl -fsS "${AUTH[@]}" \
  -d '{"message":"Reply with exactly AIPLAT_HTTP_AGENT_OK and nothing else."}' \
  "http://127.0.0.1:$PORT/v1/chat")
echo "$CHAT" | grep -q '"mode":"agent"'
echo "$CHAT" | grep -q 'AIPLAT_HTTP_AGENT_OK'

SK=$(curl -fsS "${AUTH[@]}" -d '{"params":{}}' \
  "http://127.0.0.1:$PORT/v1/skills/demo_skill")
echo "$SK" | grep -q 'AIPLAT_DEMO_HANDLER_OK'

HEALTH=$(curl -fsS -H "Authorization: Bearer $AIPLAT_HTTP_API_KEY" \
  "http://127.0.0.1:$PORT/health")
echo "$HEALTH" | grep -q '"mode":"agent"'

echo "PASS: HTTP agent + handler"
echo "PASS: live_smoke complete (model=$MODEL)"
