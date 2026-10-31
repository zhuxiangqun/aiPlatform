# Central PG / HA runbooks（ADR Accepted 有条件）

> ADR: [`ADR-CONTROL-PLANE-PG-HA.md`](../../../../reports/five-products/ADR-CONTROL-PLANE-PG-HA.md)  
> **切流前必须**完成迁移演练 + HA 演练；未绿禁止改生产默认库。

| Doc | Purpose |
|-----|---------|
| [`MIGRATION.md`](./MIGRATION.md) | SQLite → PG 迁移步骤（草案 runbook） |
| [`BACKUP_RESTORE.md`](./BACKUP_RESTORE.md) | 备份 / 恢复 |
| [`HA.md`](./HA.md) | 主备 / failover |
| [`ROLLBACK.md`](./ROLLBACK.md) | 切流失败回滚 |
| [`CUTOVER_CHECKLIST.md`](./CUTOVER_CHECKLIST.md) | 硬门清单 |
| [`PREP_STATUS.json`](./PREP_STATUS.json) | 自动检查结果（切流恒 false） |

本地演练（非生产 PG）：

```bash
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh          # #2/#3/#7 → 🟨
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh   # #4 → 🟨
bash packages/aiplat-central/scripts/pg_ha_prep_check.sh
# 跳过 docker：AIPLAT_PG_HA_SKIP_DOCKER=1
```

状态：`cutover_authorized=false` 直至 checklist 全 ✅（🟨 ≠ 授权）。

```bash
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh status
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize  # 未全 ✅ → REFUSE
```

生产 live 证据：[`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md) + `pg_ha_record_live_drill.sh`（不授权）。
