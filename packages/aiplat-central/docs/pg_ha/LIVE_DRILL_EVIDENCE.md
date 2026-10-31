# PG/HA 生产类 live 演练证据（运维填写）

> 本地/docker 🟨 **不能**替代本页。填齐并落盘 JSON 后，由运维将 `CUTOVER_CHECKLIST` 对应项改为 ✅，再跑 `pg_ha_cutover_authorize.sh authorize`。

## 必填字段

| 字段 | 说明 |
|------|------|
| `drill_id` | 唯一 id，如 `pgha-live-2026-10-30` |
| `environment` | staging / prod-canary（禁止写假环境） |
| `operator` | 执行人 |
| `started_at` / `finished_at` | ISO8601 UTC |
| `production_signed` | 运维确认后在 JSON 中置 `true`（脚本默认 `false`） |
| `items` | 见下 |

## items（与 checklist 对齐）

| key | 对应 # | 须附 |
|-----|--------|------|
| `oidc_full` | #1 | 租户登录 + admin MFA + API key 路径截图/日志引用 |
| `pg_migration` | #2 | 源/目标、行数校验、金丝雀租户 |
| `backup_restore` | #3 | 备份介质、RPO/RTO、恢复验证查询 |
| `ha_failover` | #4 | VIP/流复制、failover+回切时间线 |
| `rollback` | #7 | 回滚步骤与验证 |

## 落盘

```bash
export AIPLAT_LIVE_DRILL_ID=pgha-live-YYYYMMDD
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=alice
# 可选 JSON 文件覆盖 items：
# export AIPLAT_LIVE_DRILL_ITEMS_FILE=/path/items.json
bash packages/aiplat-central/scripts/pg_ha_record_live_drill.sh
# → docs/pg_ha/drills/live-$ID.json
```

**本脚本不修改 checklist、不授权 cutover。**
