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
- live path must have **`llm_ok_n ≥ 1`**（全 `URLError`/空回复 ≠ PASS；短跑可用 `AIPLAT_EVAL_LIVE_LLM_REPEATS=1`）

## Local evidence note（≠ 认证）

- `gemma4:12b` 全量 25×3：旧进程占 VRAM 导致后续请求挂起 — **未**作为本机通过证据
- 本机通过样本（2026-11-03）：`qwen2.5-coder:7b` · `REPEATS=1` · `llm_ok_n=25/25` · evidence `drills/local-eval-prod-live-20261103T082452Z.json`（`accuracy_claim=false`；≠ G2b / staging / security cert）

## Not claimed

≠ G2b accuracy · ≠ security certification · ≠ staging SLO
