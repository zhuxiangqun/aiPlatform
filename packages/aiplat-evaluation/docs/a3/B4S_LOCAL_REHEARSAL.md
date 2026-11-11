---
doc_type: Reference
---

# B4-S local rehearsal（≠ staging）

> Parent prep: [`B4S_PREP.md`](./B4S_PREP.md) · Runbook: [`B4S_RUNBOOK.md`](./B4S_RUNBOOK.md)

## Goal

Use laptop Docker (PG16 + MinIO + Keycloak) to rehearse migration / backup / restore / dual-read rollback **before** an independent staging host exists.

| Produces | Does not produce |
|---|---|
| `environment=local` drill JSON | staging_ready / authorize |
| Operator muscle memory + runbook | production PITR certification |

## Command

```bash
# Default: dedicated Postgres on :5434 (does not touch Option B :5433)
bash packages/aiplat-evaluation/scripts/b4s_local_rehearsal.sh

# Optional profiles
AIPLAT_EVAL_B4S_SKIP_MINIO=0 AIPLAT_EVAL_B4S_SKIP_KEYCLOAK=0 \
  bash packages/aiplat-evaluation/scripts/b4s_local_rehearsal.sh
```

## Exit

- migrate_local against Postgres OK  
- pg_dump → wipe → restore rowcount OK  
- dual-read drill OK  
- authorize status remains false  
- evidence `not_staging_evidence=true`
