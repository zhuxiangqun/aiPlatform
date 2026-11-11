---
doc_type: Reference
---

# P1 canonical — dual-path honesty

> Parent: [`P1_LOCAL.md`](./P1_LOCAL.md) · Unfreeze local Closed PASS  
> Honesty: **`accuracy_claim=false`** · package ≠ Central legacy grade · ≠ G2b

## Canonical surfaces

| Surface | Composite | text/safety/refusal |
|---|---|---|
| **Standalone Eval** (`packages/aiplat-evaluation`) | `build_composite` — **P1 engineering canonical**（`policy.composite_version=v1.1`） | safety/refusal **scored**；`text_quality` **report-only smoke**；ASR report-only |
| **Central** `AgentEvalResult.composite_score` | **legacy_7dim** (task/tool/traj/eff/recovery/safety/cost) | **report-only** (computed, not weighted); **`deprecated_for_engineering=true`** |

Machine marker on Central serialize:

```json
{
  "accuracy_claim": false,
  "scoring": {
    "schema": "eval.scoring.honesty.v0",
    "composite_policy": "legacy_7dim",
    "deprecated_for_engineering": true,
    "report_only_dimensions": ["text_quality", "content_safety", "refusal"],
    "canonical_engineering_composite": "packages/aiplat-evaluation/app/scoring/composite.py"
  }
}
```

## Why not silently reweight legacy?

Changing Central weights would move historical grades without a G2b/accuracy unlock. **ARCH v1.4** freezes this dual path as the honesty end-state: engineering → package `build_composite`; Central → labeled legacy only.

## Gate

```bash
bash packages/aiplat-evaluation/scripts/p1_canonical_gate.sh
```
