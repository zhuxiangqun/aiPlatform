---
doc_type: Reference
---

# Local chaos / backup-restore drills

> Honesty: **`accuracy_claim=false`** · `environment=local` · ≠ staging · ≠ PITR · ≠ `process_split_authorized`

## What

| Item | Value |
|---|---|
| SQLite chaos | crash unlink → restore; wipe → restore; partial dump → full recover |
| Optional B4-S | Docker PG kill/restart + wipe/restore (`AIPLAT_EVAL_CHAOS_MODE=b4s\|both`) |
| Runner | `scripts/local_chaos_drill.sh` |
| Aggregate | [`evidence/local_chaos_aggregate.v1.json`](./evidence/local_chaos_aggregate.v1.json) |

## Run

```bash
# Default: SQLite-only (CI-friendly)
bash packages/aiplat-evaluation/scripts/local_chaos_drill.sh

# With dedicated B4-S Postgres kill/restart (:5434)
AIPLAT_EVAL_CHAOS_MODE=both bash packages/aiplat-evaluation/scripts/local_chaos_drill.sh
```

Drills: `docs/a3/drills/local-eval-chaos-*.json` (gitignored).  
Committed aggregate: `docs/a3/evidence/local_chaos_aggregate.v1.json`.

## Not claimed

≠ staging host evidence · ≠ production PITR · ≠ authorize · ≠ security certification
