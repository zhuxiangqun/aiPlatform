#!/usr/bin/env bash
# Live LLM 10-task smoke: stub baseline + optional live ×3.
# NEVER sets process_split_authorized=true. accuracy_claim stays false.
#
# Stub-only (CI-safe):
#   bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh
#
# Live (Ollama / OpenAI-compatible):
#   AIPLAT_EVAL_LLM_LIVE=1 \
#   AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
#   AIPLAT_EVAL_LLM_MODEL=qwen2.5:3b \
#   AIPLAT_EVAL_LLM_TEMPERATURE=0.2 \
#   AIPLAT_EVAL_LLM_SEED=7 \
#   AIPLAT_EVAL_LLM_TIMEOUT=60 \
#   AIPLAT_EVAL_LLM_COST_PER_1K=0.0001 \
#   bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit: llm client + prompt_eval dynamic =="
PYTHONPATH=. python3 -m pytest \
  tests/test_prompt_eval_llm.py \
  tests/test_b2l_llm_dynamic_execute.py \
  tests/test_live_llm_smoke_stub.py -q --tb=line

echo "== smoke: stub (+ live if AIPLAT_EVAL_LLM_LIVE=1) =="
PYTHONPATH=. python3 scripts/live_llm_smoke.py

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "live LLM smoke gate done (authorize=false; see evidence JSON)"
