# P1 dimensions — groundedness + latency/cost

> Parent: [`P1_LOCAL.md`](./P1_LOCAL.md) · [`P1_CANONICAL.md`](./P1_CANONICAL.md)  
> Honesty: **`accuracy_claim=false`** · composite schema `v1` + **`policy.composite_version=v1.1`** · ≠ G2b  
> Versioning ADR: [`ADR_SCORE_SCHEMA_VERSIONING_V1.md`](./ADR_SCORE_SCHEMA_VERSIONING_V1.md)

## groundedness / correctness

| Field | Meaning |
|---|---|
| schema | `eval.scoring.groundedness.v0` |
| gold | `expected` and/or `context` and/or `sources` |
| scored | **true only when gold present** |
| score | token-overlap faithfulness vs gold bag (0..1) |
| correctness | exact match vs `expected` when present; else null |

Without gold: metric omitted from composite scored set; dimension still reported with `scored=false`.

## latency / cost_per_success

| Field | Meaning |
|---|---|
| schema | `eval.scoring.efficiency.v0` |
| latency_p50_ms / latency_p95_ms | nearest-rank over LLM audit `latency_ms` |
| cost_per_success | `sum(cost_estimate) / n_success` |
| n_success / n_total | success flags aligned to audit rows |

Per-run `latency_ms` / `cost_per_success` remain in metrics when audit present; the dimension aggregates batches (e.g. live smoke ×3).

## Composite versioning

| Version | Change |
|---|---|
| `eval.scoring.composite.v0` | initial engineering composite |
| `eval.scoring.composite.v1` | groundedness gold-gated; policy flags `groundedness_gold_gated` |
| `policy.composite_version=v1.1` | `text_quality` → report-only smoke（外层 schema 名仍为 `eval.scoring.composite.v1`） |

`accuracy_claim` stays false on all schemas. Cross-version trends must not mix silently.

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_p1_groundedness_latency.py \
  tests/test_p1_scoring_semantics.py \
  tests/test_p1_composite_semantics.py -q
```
