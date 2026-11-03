#!/usr/bin/env bash
# S1 live_llm against production-candidate model. NOT security certification.
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROD_MODEL="${AIPLAT_EVAL_PROD_MODEL:-}"
SMOKE_MODEL="qwen2.5:3b"
ALLOW_SMOKE="${AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL:-0}"

if [[ -z "${PROD_MODEL}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_PROD_MODEL" >&2
  exit 2
fi
if [[ "${PROD_MODEL}" == "${SMOKE_MODEL}" && "${ALLOW_SMOKE}" != "1" ]]; then
  echo "REFUSE: refuse smoke-only model without AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL=1" >&2
  exit 2
fi
if [[ -z "${AIPLAT_EVAL_LLM_BASE_URL:-}" ]]; then
  echo "REFUSE: set AIPLAT_EVAL_LLM_BASE_URL" >&2
  exit 2
fi

export AIPLAT_EVAL_S1_LIVE=1
export AIPLAT_EVAL_LLM="${AIPLAT_EVAL_LLM:-1}"
# Force prod model — ignore leftover AIPLAT_EVAL_LLM_MODEL from smoke runs.
export AIPLAT_EVAL_LLM_MODEL="$PROD_MODEL"
export AIPLAT_EVAL_LLM_TIMEOUT="${AIPLAT_EVAL_LLM_TIMEOUT:-120}"

echo "== S1 prod-candidate model=${AIPLAT_EVAL_LLM_MODEL} =="
bash "$ROOT/scripts/s1_live_gate.sh"

echo "S1 prod-model gate done (authorize=false; not security cert; accuracy_claim=false)"
