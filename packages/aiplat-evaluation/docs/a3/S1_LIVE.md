---
doc_type: Reference
---

# S1 live_llm attack pack (local)

> Parent: [`S1_LOCAL.md`](./S1_LOCAL.md)  
> Honesty: **`accuracy_claim=false`** · **`not_security_certification=true`** · no live skill tools · microVM still deferred

## What

| Item | Value |
|---|---|
| Pack | [`s1_live_attacks.v0.json`](./s1_live_attacks.v0.json) — 25 cases |
| Categories | prompt_injection / jailbreak / data_exfiltration / tool_abuse / benign_control |
| Mode | `live_llm` + `AIPLAT_EVAL_S1_LIVE=1` + docker sandbox |
| Isolation | docker wrap `--network=none` (same as fixture) |
| LLM | Independent Eval LLM (stub or Ollama); **not** Central; **not** skill tools |
| Metrics | `asr`, `leak_rate`, `false_refusal_rate` (`security_eval_v1`) |

`mode=live` (generic) stays denied. Only `live_llm` with env unlock.

## Run

```bash
# CI-safe stub
bash packages/aiplat-evaluation/scripts/s1_live_gate.sh

# Real provider
AIPLAT_EVAL_S1_LIVE=1 \
AIPLAT_EVAL_LLM=1 \
AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
AIPLAT_EVAL_LLM_MODEL=qwen2.5:3b \
bash packages/aiplat-evaluation/scripts/s1_live_gate.sh
```

Evidence drills: `docs/a3/drills/local-eval-s1-live-gate-*.json` (gitignored).  
Committed aggregate: [`evidence/s1_prod_model_aggregate.v1.json`](./evidence/s1_prod_model_aggregate.v1.json) via `scripts/s1_prod_summarize.py`.

```bash
# Production-candidate model (refuses smoke 3b unless override)
export AIPLAT_EVAL_PROD_MODEL=qwen2.5-coder:7b
export AIPLAT_EVAL_LLM=1
export AIPLAT_EVAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
bash packages/aiplat-evaluation/scripts/s1_prod_model_gate.sh
```

Local Ollama samples (not certification; 2026-11-03):

- smoke `qwen2.5:3b`: ASR≈0.22 · leak_rate≈0.67 · false_refusal=0 · `llm_ok_n=25`
- prod-candidate `qwen2.5-coder:7b` via `s1_prod_model_gate.sh`: ASR≈0.11 · leak_rate≈0.33 · false_refusal=0 · `llm_ok_n=25` · drill `drills/local-eval-s1-live-gate-20261103T084013Z.json` · aggregate committed

## Acceptance

- Pack ≥20 cases runnable under `live_llm`
- ASR / leak_rate / false_refusal_rate reported
- Failures/timeouts visible via case_details / empty responses
- **Provider honesty**: if every LLM fill fails (`llm_ok_n=0`), runner `ok=false` — empty responses must **not** PASS as a completed live pack
- Does **not** claim security certification or accuracy

## Not claimed

≠ production red-team · ≠ SOC certification · ≠ G2b accuracy · ≠ microVM
