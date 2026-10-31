# PG/HA Live Kickoff Runlog

- recorded_at: `2026-10-31T15:11:00Z`
- decision: **暂用本机** — 不宣称 staging live，不授权 cutover
- cutover_authorized: **false** (unchanged)

## Operator decision

本机 / docker ephemeral 仅维持 checklist **🟨** 与 prep 绿。  
**不做** `production_signed=true`、**不改** checklist 🟨→✅、**不跑** `pg_ha_cutover_authorize.sh authorize` 成功路径。

## Prerequisites (staging — deferred)

- [ ] `AIPLAT_PG_DSN`（预发 Postgres）— 暂缓
- [ ] `AIPLAT_OIDC_ISSUER`（预发 IdP）— 暂缓

有预发后：

```bash
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=$USER
export AIPLAT_PG_DSN='postgresql://…@staging-host/aiplat'
export AIPLAT_OIDC_ISSUER='https://…/realms/…'
bash scripts/ops_pgha_live_kickoff.sh
```

## Local / docker (allowed now)

```bash
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh
bash packages/aiplat-central/scripts/pg_ha_prep_check.sh
bash scripts/ops_live_status.sh --json
```

## Explicitly not done

- no checklist 🟨→✅
- no production_signed=true
- no cutover authorize

See [`OPS_HANDOFF.md`](../OPS_HANDOFF.md).
