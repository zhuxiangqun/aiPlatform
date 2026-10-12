#!/usr/bin/env bash
# Ensure ~/.pi/agent/models.json has an Ollama OpenAI-compatible provider for live smoke.
set -euo pipefail
AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"
EXAMPLE="$(cd "$(dirname "$0")/.." && pwd)/models.json.example"
MODEL_ID="${AIPLAT_OLLAMA_MODEL:-qwen2.5:3b}"
mkdir -p "$AGENT_DIR"
TARGET="$AGENT_DIR/models.json"
if [[ -f "$TARGET" ]] && grep -q '"ollama"' "$TARGET" 2>/dev/null; then
  echo "OK: $TARGET already has ollama provider"
  exit 0
fi
if [[ -f "$TARGET" ]] && [[ -s "$TARGET" ]] && ! grep -q '^{\s*}' "$TARGET"; then
  echo "WARN: $TARGET exists without ollama — leave untouched; set AIPLAT_PI_MODEL manually"
  exit 0
fi
# shellcheck disable=SC2002
sed "s/qwen2.5:3b/${MODEL_ID}/g" "$EXAMPLE" >"$TARGET"
echo "OK: wrote $TARGET (model=$MODEL_ID)"
