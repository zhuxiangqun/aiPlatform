# Evaluation standalone migrations (A2 / B1-L)

Portable SQL for `AIPLAT_EVAL_DB_URL` — **SQLite** (default) or **Postgres** (`postgresql://…`).
Mirrors charter `eval.store.v0` entities.

```bash
bash packages/aiplat-evaluation/scripts/migrate_local.sh
# or: service auto-migrates on startup
# Postgres example:
#   AIPLAT_EVAL_DB_URL=postgresql://eval:eval_local@127.0.0.1:5433/eval bash …/migrate_local.sh
```

| File | Version |
|------|---------|
| `0001_eval_store_v0.sql` | `eval.store.v0` |
| `0002_tenant_id.sql` | tenant columns + indexes |
| `0003_eval_jobs.sql` | B2-L job queue (`eval_jobs`) |
| `0004_eval_jobs_lease.sql` | `leased_by` for claim/heartbeat |
| `0005_eval_jobs_result.sql` | `result_json` runner collect output |

**Honesty**: local engineering only; `process_split_authorized=false`; no production data migration.
