# 预发就绪 Gate（排在 PG/HA live 之前）

> **目的**：把「工程完成」与「环境未就绪」分开。未满足本 Gate → **正式 defer**，禁止跑 staging live / sign / authorize。  
> **不**改 checklist 硬门；**不**把 local/docker 标成 staging。

## 输入（全部齐才算 ready）

| # | 项 | 验收 |
|---|----|------|
| 1 | Staging Postgres DSN | `AIPLAT_PG_DSN` 指向预发实例；TLS；独立库；最小权限用户；备份/PITR 可用 |
| 2 | OIDC | `AIPLAT_OIDC_ISSUER` 可达；client + redirect；admin MFA；测试租户/用户 |
| 3 | Operator / 窗口 | 指定 operator；变更窗口；回滚预案书面就绪 |
| 4 | 环境名 | `AIPLAT_LIVE_DRILL_ENV=staging`（或 `prod-canary`）；禁止 `scaffold` / `local` / `docker-ephemeral` |

## 输出

| 字段 | 含义 |
|------|------|
| `staging_ready=true` | 上表齐套，允许 `ops_pgha_live_kickoff.sh` 进入 record 路径 |
| `staging_ready=false` | 正式 defer（见 [`LOCAL_DEFER.md`](./LOCAL_DEFER.md)）；硬门保持 false |

当前：**`staging_ready=false`**（DSN/OIDC UNSET；kickoff exit 2）。

## 未满足时

1. 记 blockers 到 [`PGHA_LIVE_RUNLOG.md`](./PGHA_LIVE_RUNLOG.md)  
2. 保持 `cutover_authorized=false` 等硬门  
3. 主轨转不依赖预发的工作（如 Pi D1）  
4. **当前默认**：环境方案 B 全轨 [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · [`LOCAL_STAGING.md`](./LOCAL_STAGING.md)（`local-*.json` / `local_signed`）；**不得** `production_signed` / authorize；**不得**把本机 B 标成本 Gate 已满足

齐套后：`bash scripts/ops_pgha_live_kickoff.sh` → 交接卡 live → sign → authorize。
