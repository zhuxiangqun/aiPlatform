---
doc_type: Reference
---

# Multi-turn / session v1 (5–8 turns)

> Parent: [`SESSION_V0.md`](./SESSION_V0.md)  
> Honesty: **`accuracy_claim=false`** · ≠ full dialogue / agent horizon · ≠ G2b

## What

| Item | Value |
|---|---|
| Runner | same `session_eval` (payload `profile: v1`) |
| Turns | **5–8** |
| Schema | `eval.scoring.session.v1` |
| Pack | [`session_tasks.v1.json`](./session_tasks.v1.json) |

Prior turns remain plain-text context (no tools).

## Run

```bash
bash packages/aiplat-evaluation/scripts/session_v1_gate.sh
```

## Acceptance

- ≥2 fixture sessions with 5–8 turns and `session_pass=true`
- `dimensions.session.profile == "v1"`
- `accuracy_claim=false`

## Not claimed

≠ long-horizon agent eval · ≠ G2b · ≠ production conversation quality
