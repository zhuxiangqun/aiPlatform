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

Evidence: `docs/a3/drills/local-eval-s1-live-gate-*.json` (gitignored drills dir).

## Acceptance

- Pack ≥20 cases runnable under `live_llm`
- ASR / leak_rate / false_refusal_rate reported
- Failures/timeouts visible via case_details / empty responses
- Does **not** claim security certification or accuracy

## Not claimed

≠ production red-team · ≠ SOC certification · ≠ G2b accuracy · ≠ microVM
