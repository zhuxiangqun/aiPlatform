# Multi-turn / session v0 (2–3 turns)

> Parent: [`P1_LOCAL.md`](./P1_LOCAL.md) · [`P1_DIMENSIONS.md`](./P1_DIMENSIONS.md)  
> Honesty: **`accuracy_claim=false`** · ≠ full dialogue eval · ≠ G2b

## What

| Item | Value |
|---|---|
| Runner | `session_eval` (B2 allowlist; no tools) |
| Turns | **2–3** (`MIN=2`, `MAX=3`) |
| Schema | `eval.scoring.session.v0` |
| Pack | [`session_tasks.v0.json`](./session_tasks.v0.json) |
| Metrics | `turn_success_rate`, `session_pass`, `turns_n` / `turns_ok` |

Optional LLM fills missing `actual` per turn (`AIPLAT_EVAL_LLM`); prior turns are plain-text context, not a tool loop.

## Run

```bash
bash packages/aiplat-evaluation/scripts/session_v0_gate.sh
```

## Acceptance

- ≥2 fixture sessions pass with `session_pass=true`
- Scoring attaches `dimensions.session`
- `accuracy_claim=false`

## Not claimed

≠ long-horizon agent eval · ≠ G2b accuracy · ≠ production conversation quality
