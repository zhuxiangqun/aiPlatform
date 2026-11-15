---
doc_type: Reference
---

# Eval store surface v0 — honest subset

> Honesty: schema entity enum ≠ standalone API surface · Central cohost store is fuller · `process_split_authorized=false`

## Contract vs implementation

[`eval_store.schema.json`](../../contracts/schemas/eval_store.schema.json) defines **8 entity shapes** (set / task / run / judgment / label / report / judge / gate). Migrations create matching tables.

**Standalone package API** (`packages/aiplat-evaluation/app/store/`) currently implements:

| Surface | Status |
|---------|--------|
| `eval_set` CRUD (create/get/list) | ✅ |
| `eval_report` CRUD (create/get/list) + scoring stamp | ✅ |
| `eval_jobs` queue (lease/claim; `payload_json` only) | ✅ |
| `eval_task` / `eval_run` / `eval_judgment` / `eval_label` / `eval_judge` / `eval_gate` | DDL only — **no** package store methods / HTTP routes |

**Central cohost** (`aiPlat-core/core/apps/eval/service/store.py` via `/api/platform/apps/eval/store/*`) remains the maintenance UI SSOT for tasks/judges/gates until A3 split is authorized.

## payload_uri

`EVAL_RUNTIME_CONTRACT` mentions large-object `payload_uri`. **v0 jobs use `payload_json` only** (see migration `0003_eval_jobs.sql`). Object URI offload is deferred; do not claim Object Store wiring.

## Non-goals

- Silently shrinking the schema enum to hide the gap (shapes stay for forward compat)
- Pretending package store is the full charter §5.2 resource model
- Flipping `process_split_authorized`
