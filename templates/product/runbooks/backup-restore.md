# Backup / restore (stub)

## Backup

- Postgres: `pg_dump` per product database/schema
- Objects: S3/MinIO prefix listing + versioned copy
- Dev/SQLite: copy file under `$AIPLAT_HOME` only (never real user home escape)

## Restore

1. Stop writers.
2. Restore DB + objects to target version.
3. Start; `/readyz`; contract smoke.

## Retention

Document RPO/RTO in D2 security/admin pack — not in P0.
