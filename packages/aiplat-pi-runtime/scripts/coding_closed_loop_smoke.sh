#!/usr/bin/env bash
# Factory-in way-4 smoke: Pi print-mode coding turn inside a temp-dir "sandbox".
# Does NOT wire into PipelineEngine. Requires pi + reachable model (Ollama default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${AIPLAT_PI_MODEL:-ollama/qwen2.5:3b}"
MARKER="AIPLAT_PI_CODING_OK"

if [[ "${AIPLAT_SKIP_CODING_SMOKE:-}" == "1" ]]; then
  echo "SKIP: AIPLAT_SKIP_CODING_SMOKE=1"
  exit 0
fi

if ! command -v pi >/dev/null 2>&1; then
  echo "FAIL: pi CLI not found"
  exit 1
fi

if [[ -z "${AIPLAT_PI_BASE_URL:-}" ]]; then
  if ! curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "FAIL: Ollama not at :11434 (set AIPLAT_PI_BASE_URL or AIPLAT_SKIP_CODING_SMOKE=1)"
    exit 1
  fi
fi

# Ensure CLI models.json has ollama when using default provider
bash "$ROOT/scripts/ensure_ollama_models_json.sh" >/dev/null || true

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/aiplat-pi-coding.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

printf 'hello\n' >"$WORKDIR/note.txt"

PROMPT="Edit note.txt: append a new line that is exactly the token ${MARKER} and nothing else on that line. Do not create other files."

echo "== Pi coding turn in sandbox $WORKDIR (model=$MODEL) =="
set +e
python3 "$ROOT/scripts/pi_coding_exec.py" \
  --cwd "$WORKDIR" \
  --model "$MODEL" \
  --timeout "${AIPLAT_CODING_SMOKE_TIMEOUT:-180}" \
  --prompt "$PROMPT"
RC=$?
set -e

if [[ "$RC" -ne 0 ]]; then
  echo "FAIL: pi_coding_exec exit $RC"
  echo "----- note.txt -----"
  cat "$WORKDIR/note.txt" || true
  exit "$RC"
fi

if ! grep -qF -- "$MARKER" "$WORKDIR/note.txt"; then
  echo "FAIL: marker not written into note.txt"
  echo "----- note.txt -----"
  cat "$WORKDIR/note.txt" || true
  exit 1
fi

echo "PASS: coding_closed_loop smoke (temp-dir sandbox + Pi print-mode)"
echo "NOTE: PolicyGate/done_verify/review_gate remain outside Pi; engine not wired."
