# Live LLM 10-task smoke (local)

> Parent: [`LLM_LOCAL.md`](./LLM_LOCAL.md) · P1 canonical [`P1_CANONICAL.md`](./P1_CANONICAL.md)  
> Honesty: **`accuracy_claim=false`** · ≠ G2b · ≠ staging authorize · ≠ security cert

## What

| Item | Value |
|---|---|
| Tasks | 10 — Agent×3 / Skill×3 / Prompt×2 / KB×2 ([`live_llm_tasks.v0.json`](./live_llm_tasks.v0.json)) |
| Stub | 1 pass per task (CI-safe baseline) |
| Live | optional ×3 per task when `AIPLAT_EVAL_LLM_LIVE=1` |
| Runner | `prompt_eval` + independent OpenAI-compatible provider |
| Evidence | `docs/a3/drills/local-eval-live-llm-*.json` |

Records per run: model, temperature, seed, timeout, tokens, cost_estimate, latency, status/detail (failures/timeouts visible).

Progress: stderr per live task (`live_rN i/N id=… ok=… lat_ms=…`) so hung Ollama runs are not silent.

## Run

```bash
# CI / default — stub only
bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh

# Live (example: local Ollama)
AIPLAT_EVAL_LLM_LIVE=1 \
AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
AIPLAT_EVAL_LLM_MODEL=qwen2.5:3b \
AIPLAT_EVAL_LLM_TEMPERATURE=0.2 \
AIPLAT_EVAL_LLM_SEED=7 \
AIPLAT_EVAL_LLM_TIMEOUT=60 \
AIPLAT_EVAL_LLM_COST_PER_1K=0.0001 \
AIPLAT_EVAL_LIVE_LLM_COST_CAP=1.0 \
bash packages/aiplat-evaluation/scripts/live_llm_smoke.sh
```

## Acceptance

- 10/10 tasks have stub results
- If live requested: 10/10 have live results (fail/timeout still count as visible outcomes)
- If live requested: **`llm_ok_n ≥ 1`** — all-`provider_error` / empty fills must **not** PASS (same honesty as S1)
- `total_cost_estimate ≤ AIPLAT_EVAL_LIVE_LLM_COST_CAP` (default 1.0)
- `accuracy_claim=false`; provider must not look like Central `:8000`

## Not claimed

Live smoke ≠ production LLM certification · ≠ accuracy · ≠ G2b κ.
