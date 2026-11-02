# P1 — scoring semantics (local)

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

Every `runner_result` attaches `scoring` (`eval.scoring.semantics.v0`).

## Tests / gate

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest tests/test_p1_scoring_semantics.py -q
bash packages/aiplat-evaluation/scripts/p1_local_gate.sh
```
