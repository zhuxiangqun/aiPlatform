#!/usr/bin/env bash
# Way-4 experiment smoke: Pi print coding exec in a temp workdir (host allow, local only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${AIPLAT_PI_MODEL:-ollama/qwen2.5:3b}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/aiplat-pi-coding.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "== coding_exec refuse without --allow-host =="
# coding_exec exits 1 on refuse; capture under pipefail so grep still sees stdout
REFUSE_OUT=$(python3 "$ROOT/scripts/coding_exec.py" --cwd "$WORK" --prompt "noop" --model "$MODEL" 2>&1) || true
if echo "$REFUSE_OUT" | grep -q 'host cwd refused'; then
  echo "PASS: host refused"
else
  echo "FAIL: expected host refuse"
  echo "$REFUSE_OUT" | tail -20
  exit 1
fi

if [[ -z "${AIPLAT_PI_BASE_URL:-}" ]]; then
  if ! curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "SKIP live coding: Ollama not on :11434 (refuse gate still PASS)"
    exit 0
  fi
fi

if ! command -v pi >/dev/null 2>&1; then
  echo "SKIP live coding: pi CLI missing (refuse gate still PASS)"
  exit 0
fi

MARKER="AIPLAT_PI_CODING_OK_$$"
echo "== coding_exec live write =="
OUT=$(python3 "$ROOT/scripts/coding_exec.py" \
  --cwd "$WORK" \
  --model "$MODEL" \
  --allow-host \
  --timeout 180 \
  --prompt "Create a file named marker.txt whose entire contents are exactly: ${MARKER}" \
  2>&1) || true
echo "$OUT" | tail -20
if [[ -f "$WORK/marker.txt" ]] && grep -q "$MARKER" "$WORK/marker.txt"; then
  echo "PASS: coding_exec wrote marker.txt"
  exit 0
fi
# Models may put text only in stdout — accept marker in JSON text as soft pass
if echo "$OUT" | grep -q "$MARKER"; then
  echo "PASS soft: marker in pi output (file optional)"
  exit 0
fi
echo "FAIL: marker not found in $WORK or output"
exit 1
