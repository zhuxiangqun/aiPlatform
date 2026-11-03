# P1 canonical — dual-path honesty

> Parent: [`P1_LOCAL.md`](./P1_LOCAL.md) · Unfreeze local Closed PASS  
> Honesty: **`accuracy_claim=false`** · package ≠ Central legacy grade · ≠ G2b

## Canonical surfaces

| Surface | Composite | text/safety/refusal |
|---|---|---|
| **Standalone Eval** (`packages/aiplat-evaluation`) | `build_composite` — **P1 engineering canonical** | **scored** (ASR report-only) |
| **Central** `AgentEvalResult.composite_score` | **legacy_7dim** (task/tool/traj/eff/recovery/safety/cost) | **report-only** (computed, not weighted) |

Machine marker on Central serialize:

```json
{
  "accuracy_claim": false,
  "scoring": {
    "schema": "eval.scoring.honesty.v0",
    "composite_policy": "legacy_7dim",
    "report_only_dimensions": ["text_quality", "content_safety", "refusal"],
    "canonical_engineering_composite": "packages/aiplat-evaluation/app/scoring/composite.py"
  }
}
```

## Why not silently reweight legacy?

Changing Central weights would move historical grades without a G2b/accuracy unlock. This slice **labels** the dual path instead of migrating weights.

## Gate

```bash
bash packages/aiplat-evaluation/scripts/p1_canonical_gate.sh
```
