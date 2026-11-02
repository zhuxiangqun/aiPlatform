# Evaluation standalone migrations (A2 local)

SQLite-first schema for `AIPLAT_EVAL_DB_URL`. Mirrors charter `eval.store.v0` entities.

```bash
bash packages/aiplat-evaluation/scripts/migrate_local.sh
# or: service auto-migrates on startup (A2)
```

| File | Version |
|------|---------|
| `0001_eval_store_v0.sql` | `eval.store.v0` |

**Honesty**: local engineering only; `process_split_authorized=false`; no production data migration.
