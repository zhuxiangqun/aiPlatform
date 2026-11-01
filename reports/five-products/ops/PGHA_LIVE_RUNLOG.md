# PG/HA Live Kickoff Runlog

- recorded_at: `2026-10-31T23:35:04Z`（初审）
- reviewed_at: `2026-11-01T09:33+08:00`（按 [`STAGING_REVIEW_2026-11-08.md`](./STAGING_REVIEW_2026-11-08.md) 开审）
- drill_id: `pgha-live-20261031`
- environment: **intent was staging；未进入 record**（本机 DSN ≠ 预发）
- operator: `apple`
- decision: **续 defer（路径 B）** — 复审仍无独立预发；kickoff `can_record=false`
- cutover_authorized: **false** (unchanged)
- staging_ready: **false**（[`STAGING_READY.md`](./STAGING_READY.md)）
- review_by: **2026-11-15**（续）

## Prerequisites（2026-11-01 复审探测）

- note: `AIPLAT_PG_DSN` 指向 `127.0.0.1:5433`（Option B local）→ **不计** staging
- note: `AIPLAT_OIDC_ISSUER` / `OIDC_ISSUER` **UNSET**
- note: shell 中 `AIPLAT_LIVE_DRILL_ENV=staging` 与本机 DSN 并存 → **标签不诚实；不得 unlock**
- note: docker daemon 本次探测不可用；即便可用，local/docker ≠ live authorize 证据

## Blockers（must clear before live / sign / authorize）

- [ ] `AIPLAT_PG_DSN` 指向**独立预发** Postgres（非 `127.0.0.1` / 本机 Docker；含 TLS / 备份 / 最小权限）
- [ ] missing `AIPLAT_OIDC_ISSUER` (or `OIDC_ISSUER`) for tenant login / admin MFA / 测试租户
- [ ] operator + 变更窗口 + 回滚预案书面就绪
- [ ] `AIPLAT_LIVE_DRILL_ENV=staging`（或 `prod-canary`）且 DSN/OIDC 与标签一致；禁止用 local DSN 挂 staging 名

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

See [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) · [`STAGING_REVIEW_2026-11-08.md`](./STAGING_REVIEW_2026-11-08.md).
