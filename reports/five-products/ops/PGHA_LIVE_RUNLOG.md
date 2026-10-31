# PG/HA Live Kickoff Runlog

- recorded_at: `2026-10-31T23:35:04Z`
- drill_id: `pgha-live-20261031`
- environment: `staging`（意图；**未实际进入 record**）
- operator: `apple`
- decision: **正式 defer（路径 B）** — 预发未齐；kickoff exit 2 = 硬门按设计生效
- cutover_authorized: **false** (unchanged)
- staging_ready: **false**（[`STAGING_READY.md`](./STAGING_READY.md)）
- review_by: **2026-11-08**

## Prerequisites（探测结果）

- note: 本机 `docker` 可用；local/docker rehearsal **≠** live authorize 证据
- note: `AIPLAT_PG_DSN` / `DATABASE_URL` **UNSET**
- note: `AIPLAT_OIDC_ISSUER` / `OIDC_ISSUER` **UNSET**

## Blockers（must clear before live / sign / authorize）

- [ ] missing `AIPLAT_PG_DSN` (or `DATABASE_URL`) for staging/prod-canary Postgres（含 TLS / 备份 / 最小权限）
- [ ] missing `AIPLAT_OIDC_ISSUER` (or `OIDC_ISSUER`) for tenant login / admin MFA / 测试租户
- [ ] operator + 变更窗口 + 回滚预案书面就绪
- [ ] `AIPLAT_LIVE_DRILL_ENV=staging`（或 `prod-canary`；禁止 scaffold/local/docker-ephemeral）

## 复审条件（全部齐 → 重跑 kickoff）

1. 预发 PG DSN 可用（TLS、备份/PITR、最小权限、独立库）  
2. OIDC issuer + client + admin MFA + 测试租户可达  
3. operator / 窗口 / 回滚预案确认  
4. 上三项齐后：`staging_ready=true`，再执行：

```bash
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=$USER
export AIPLAT_PG_DSN='postgresql://…@staging-host/aiplat'
export AIPLAT_OIDC_ISSUER='https://…/realms/…'
bash scripts/ops_pgha_live_kickoff.sh
# → record → ops_live_sign → checklist 🟨→✅ → cutover_authorize
```

## Explicitly not done

- no checklist 🟨→✅
- no production_signed=true
- no cutover authorize
- no fake staging DSN/OIDC

See [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) · [`STAGING_READY.md`](./STAGING_READY.md) · [`OPS_HANDOFF.md`](../OPS_HANDOFF.md).
