---
doc_type: Reference
---

# Production-model live baseline（local）

> Honesty: **`accuracy_claim=false`** · `environment=local` · ≠ 3B smoke alone · ≠ staging authorize

## What

| Item | Value |
|---|---|
| Pack | [`prod_live_tasks.v0.json`](./prod_live_tasks.v0.json) — 25 tasks |
| Repeats | 3 (latency / token variance) |
| Runner | `scripts/prod_live_baseline.sh` → `live_llm_smoke.py` |
| Aggregate | [`evidence/prod_live_aggregate.v1.json`](./evidence/prod_live_aggregate.v1.json) via `scripts/prod_live_summarize.py` |
| Compare | optional prior 3B smoke / 7b×1 drill JSON |

## Run

```bash
# Required: your real eval/production candidate model (not the 3B smoke default)
export AIPLAT_EVAL_LLM_LIVE=1
export AIPLAT_EVAL_LLM=http
export AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1   # or OpenAI-compatible API
export AIPLAT_EVAL_PROD_MODEL=qwen2.5-coder:7b              # example — set yours
export AIPLAT_EVAL_LLM_MODEL="$AIPLAT_EVAL_PROD_MODEL"
export AIPLAT_EVAL_LLM_TEMPERATURE=0.2
export AIPLAT_EVAL_LLM_SEED=7
export AIPLAT_EVAL_LLM_TIMEOUT=120
export AIPLAT_EVAL_LIVE_LLM_TASKS=packages/aiplat-evaluation/docs/a3/prod_live_tasks.v0.json
export AIPLAT_EVAL_LIVE_LLM_REPEATS=3
# Localhost providers: avoid proxy/sandbox blocking
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost

bash packages/aiplat-evaluation/scripts/prod_live_baseline.sh
```

Evidence drill: `docs/a3/drills/local-eval-prod-live-*.json` (gitignored).  
Committed aggregate: `docs/a3/evidence/prod_live_aggregate.v1.json`.

## Acceptance

- model / version / temperature / seed recorded
- per-task latency + tokens + cost_estimate + fail/timeout visible
- `accuracy_claim=false`
- refuses `AIPLAT_EVAL_PROD_MODEL` empty or equal to smoke-only `qwen2.5:3b` unless `AIPLAT_EVAL_PROD_ALLOW_SMOKE_MODEL=1`
- **forces** `AIPLAT_EVAL_LLM_MODEL=$AIPLAT_EVAL_PROD_MODEL`（忽略 shell 里残留的 3B `AIPLAT_EVAL_LLM_MODEL`）
- live path must have **`llm_ok_n ≥ 1`**（全 `URLError`/空回复 ≠ PASS；短跑可用 `AIPLAT_EVAL_LIVE_LLM_REPEATS=1`）

## Local evidence note（≠ 认证）

| Run | Model | Repeats | llm_ok_n | Notes |
|---|---|---:|---:|---|
| 2026-11-03 | `qwen2.5-coder:7b` | 1 | 25/25 | first local pass sample |
| **2026-11-04** | `qwen2.5-coder:7b` | **3** | **75/75** | full 25×3; p50≈1056ms p95≈4521ms; cost≈0.0005; aggregate committed |
| — | `gemma4:12b` 25×3 | — | — | VRAM hang historically — **not** used as pass evidence |

## Not claimed

≠ G2b accuracy · ≠ security certification · ≠ staging SLO · ≠ remote prod API certification (this run used local Ollama)
