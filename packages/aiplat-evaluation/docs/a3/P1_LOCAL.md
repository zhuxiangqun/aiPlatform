# P1 — scoring semantics + engineering composite (local)

> Plan: [`eval-production-independent-service.md`](../../../../docs/architecture/plans/eval-production-independent-service.md) §7.1  
> Honesty: **`accuracy_claim=false`** until G2b · quality/safety/efficiency/security ≠ accuracy

## Families

| Family | Examples | Notes |
|---|---|---|
| accuracy | *(empty until G2b)* | never claimed in this slice |
| quality | `exact_match`, `text_quality`, `groundedness` | engineering scores |
| safety | `content_safety`, `refusal` | not S1 ASR |
| efficiency | `latency_ms`, `cost_estimate`, `cost_per_success` | from LLM audit when present |
| security | `asr` | owned by S1; classified for honesty |

Every `runner_result` attaches `scoring` (`eval.scoring.semantics.v0`) including `composite`.

## Composite policy (explicit)

| Role | Metrics |
|---|---|
| **Scored** into engineering composite 0–100 | `text_quality`, `content_safety`, `refusal`, `groundedness`, `exact_match`, `pass`, `coverage`, normalized `latency_ms`/`cost_*`/`steps` |
| **Report-only** (not weighted) | `asr` / security family, `accuracy`, `winner`, counts (`gold_n`, `hit_count`, …) |

Weights (renormalized over present families): quality 0.55 · safety 0.25 · efficiency 0.20.

This composite is **not** G2b accuracy. Dual-path honesty: see [`P1_CANONICAL.md`](./P1_CANONICAL.md) — package `build_composite` is engineering **canonical**; Central `AgentEvalResult.composite_score` stays **legacy_7dim** with text/safety/refusal **report-only**.

## P1.1 / P1.2 runners

| Runner | Extra P1 metrics |
|---|---|
| `prompt_eval` | text_quality / groundedness / safety / efficiency (LLM audit) |
| `kb_rag` | groundedness vs hit texts + text_quality + content_safety |
| `arena` | avg text_quality + min content_safety (pure-text only) |
| `code_review_gold` | exact_match / coverage / groundedness + safety |
| `replay_trace` | steps + optional latency_ms (efficiency) |

## Tests / gate

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_p1_scoring_semantics.py \
  tests/test_p1_1_kb_arena_metrics.py \
  tests/test_p1_2_gold_replay_metrics.py \
  tests/test_p1_composite_semantics.py -q
bash packages/aiplat-evaluation/scripts/p1_local_gate.sh
```
