# PG/HA 切流硬门清单

> `cutover_authorized` 仅当下列全部为 ✅（🟨 = 部分自动绿，仍须人工 OIDC/生产演练）。  
> 刷新：`pg_ha_local_rehearsal.sh` → `pg_ha_ha_failover_rehearsal.sh` → `pg_ha_prep_check.sh`

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | 租户/OIDC 回归绿 | 平台 | 🟨 |
| 2 | PG 迁移演练记录（环境/日期/结果） | 运维 | 🟨 |
| 3 | 备份恢复演练记录 | 运维 | 🟨 |
| 4 | HA failover + 回切演练记录 | 运维 | 🟨 |
| 5 | 契约耦合确认（无跨库直读） | 架构 | ✅ |
| 6 | Chart / 发布节奏独立 | 运维 | ✅ |
| 7 | 回滚演练一次 | 运维 | 🟨 |

`cutover_authorized: false`

## 自动 vs 人工

| 自动（prep / local / docker） | 仍须人工 live drill |
|------------------------------|---------------------|
| #5 platform apps 无 `core.harness` 直导 | #2 **生产类** PG 迁移 |
| #6 chart skeleton + cutover=false 注解 | #3 **生产** PG 备份恢复 |
| #1 MFA 单测（🟨，非完整 OIDC） | #4 **生产** HA / VIP / 流复制 |
| #3/#7 本地 SQLite 演练（🟨） | #7 生产类回滚 / 完整 OIDC |
| #2 DSN 或 docker ephemeral schema（🟨） | |
| #4 docker ephemeral failover/failback（🟨，无 VIP） | |
