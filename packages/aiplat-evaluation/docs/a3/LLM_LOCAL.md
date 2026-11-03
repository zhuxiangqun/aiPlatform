# Eval Worker LLM (local optional + dynamic gate)

> Contract: [`EVAL_MODEL_GATEWAY.md`](../../../../docs/architecture/plans/EVAL_MODEL_GATEWAY.md)  
> Honesty: `accuracy_claim=false` · no Central HTTP · no `core.harness` · not staging authorize

## Enable

| Env | Meaning |
|---|---|
| `AIPLAT_EVAL_LLM=0` | default — deterministic / require `payload.actual` |
| `AIPLAT_EVAL_LLM=stub` | offline stub (`AIPLAT_EVAL_LLM_STUB_OUTPUT`) |
| `AIPLAT_EVAL_LLM=1` + `AIPLAT_EVAL_LLM_BASE_URL` | OpenAI-compatible `POST …/chat/completions` |

Also: `AIPLAT_EVAL_LLM_API_KEY`, `AIPLAT_EVAL_LLM_MODEL`, `AIPLAT_EVAL_LLM_TIMEOUT`, `AIPLAT_EVAL_LLM_COST_PER_1K`.

Provider must be **independent of Central process** (same physical host OK if separate lifecycle).  
`AIPLAT_EVAL_LLM_BASE_URL` that looks like Central (`:8000`, `/api/core/`, `/api/platform/`) is **refused**.

## Dynamic gate

```bash
# CI / default — stub Worker e2e (always)
bash packages/aiplat-evaluation/scripts/b2l_llm_dynamic_gate.sh

# Optional live independent provider (Ollama/vLLM/OpenAI-compatible)
AIPLAT_EVAL_LLM_LIVE=1 \
AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
bash packages/aiplat-evaluation/scripts/b2l_llm_dynamic_gate.sh
```

Evidence: `docs/a3/drills/local-eval-b2l-llm-dynamic-gate-*.json`  
`live_ok=true` only when an independent provider answered; stub path alone ≠ production live LLM certification.

## 10-task live smoke (stub vs live ×3)

See [`LIVE_LLM_SMOKE.md`](./LIVE_LLM_SMOKE.md) — Agent/Skill/Prompt/KB pack, variance, cost cap; evidence `local-eval-live-llm-*.json`.

```bash
bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh
# live:
AIPLAT_EVAL_LLM_LIVE=1 AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
AIPLAT_EVAL_LLM_MODEL=qwen2.5:3b bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh
```

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_prompt_eval_llm.py \
  tests/test_b2l_llm_dynamic_execute.py \
  tests/test_live_llm_smoke_stub.py -q
```
