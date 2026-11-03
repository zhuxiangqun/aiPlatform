# Production-model live baseline（local）

> Honesty: **`accuracy_claim=false`** · `environment=local` · ≠ 3B smoke alone · ≠ staging authorize

## What

| Item | Value |
|---|---|
| Pack | [`prod_live_tasks.v0.json`](./prod_live_tasks.v0.json) — 25 tasks |
| Repeats | 3 (latency / token variance) |
| Runner | `scripts/prod_live_baseline.sh` → `live_llm_smoke.py` |
| Compare | optional prior 3B smoke evidence JSON |

## Run

```bash
# Required: your real eval/production candidate model (not the 3B smoke default)
export AIPLAT_EVAL_LLM_LIVE=1
export AIPLAT_EVAL_LLM=1
export AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1   # or OpenAI-compatible API
export AIPLAT_EVAL_PROD_MODEL=gemma4:12b                   # example — set yours
export AIPLAT_EVAL_LLM_MODEL="$AIPLAT_EVAL_PROD_MODEL"
export AIPLAT_EVAL_LLM_TEMPERATURE=0.2
export AIPLAT_EVAL_LLM_SEED=7
export AIPLAT_EVAL_LLM_TIMEOUT=120
export AIPLAT_EVAL_LIVE_LLM_TASKS=packages/aiplat-evaluation/docs/a3/prod_live_tasks.v0.json
export AIPLAT_EVAL_LIVE_LLM_REPEATS=3

bash packages/aiplat-evaluation/scripts/prod_live_baseline.sh
```

Evidence: `docs/a3/drills/local-eval-prod-live-*.json` (gitignored drills).

## Acceptance

- model / version / temperature / seed recorded
- per-task latency + tokens + cost_estimate + fail/timeout visible
- `accuracy_claim=false`
- refuses `AIPLAT_EVAL_PROD_MODEL` empty or equal to smoke-only `qwen2.5:3b` unless `AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL=1`
- **forces** `AIPLAT_EVAL_LLM_MODEL=$AIPLAT_EVAL_PROD_MODEL`（忽略 shell 里残留的 3B `AIPLAT_EVAL_LLM_MODEL`）

## Not claimed

≠ G2b accuracy · ≠ security certification · ≠ staging SLO
