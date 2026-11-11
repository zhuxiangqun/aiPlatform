---
doc_type: Reference
---

# B4-S runbook — local rehearsal → future staging

> Honesty: steps marked **local** produce `environment=local` evidence only.  
> Staging live / authorize requires an independent host + signed drill (see [`B4S_PREP.md`](./B4S_PREP.md)).

## 0. Preconditions

| Local rehearsal | Real B4-S staging |
|---|---|
| Docker Desktop / Engine | Separate VM/cluster |
| `compose/docker-compose.b4s-local.yml` | Durable disk + network isolation |
| Port **5434** free for b4s PG (leaves Option B `:5433` alone) | Real DSN / OIDC / object store |

## 1. Bring up data plane（local）

```bash
cd packages/aiplat-evaluation
docker compose -f compose/docker-compose.b4s-local.yml up -d
docker compose -f compose/docker-compose.b4s-local.yml ps
```

Expect: postgres healthy · minio up · keycloak up (dev).

## 2. Migrate EvalStore → Postgres

```bash
export AIPLAT_EVAL_DB_URL='postgresql://eval:eval_local@127.0.0.1:5434/eval'
bash scripts/migrate_local.sh
```

## 3. Dual-read fixture（already B3-L）

```bash
bash scripts/b3l_dual_read_drill.sh
```

## 4. Backup → destroy → restore（Postgres）

Automated in `scripts/b4s_local_rehearsal.sh` (pg_dump → wipe → restore → row count check).

Manual:

```bash
COMPOSE="docker compose -f compose/docker-compose.b4s-local.yml"
$COMPOSE exec -T postgres pg_dump -U eval eval > /tmp/eval_b4s_backup.sql
$COMPOSE exec -T postgres psql -U eval -d eval -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
$COMPOSE exec -T postgres psql -U eval -d eval < /tmp/eval_b4s_backup.sql
```

## 5. Cut back to cohost pointer（rollback）

Dual-read pointer rollback is covered by B3-L drill (`write_read_pointer` → cohost).  
On staging: document the same pointer flip + traffic drain before authorize.

## 6. Keycloak JWKS smoke（local）

```bash
# Optional profile: COMPOSE_PROFILES=keycloak
# Or reuse Option B Keycloak on :8081
curl -fsS "http://127.0.0.1:8081/realms/master/protocol/openid-connect/certs" | head
# Wire later: AIPLAT_EVAL_JWKS_URL=...
```

## 7. Evidence & honesty

```bash
bash scripts/b4s_local_rehearsal.sh
# → docs/a3/drills/local-eval-b4s-rehearsal-*.json
# environment=local · process_split_authorized=false · not_staging_evidence=true
```

## 8. When real staging host arrives

1. Confirm host per [`B4S_PREP.md`](./B4S_PREP.md)  
2. Open `ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING`  
3. Re-run this runbook against **staging** DSN/OIDC/MinIO  
4. Sign live drill — only then B6 authorize path
