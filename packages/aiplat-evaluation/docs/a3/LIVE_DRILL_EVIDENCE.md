# Evaluation A3 生产类 live 拆分演练证据

> 本地 SQLite/prefix 🟨 **不能**替代。证据齐后运维将 `SPLIT_CHECKLIST` #4（及 #1 若需）改为 ✅，再 `a3_split_authorize.sh authorize`。

## 必填

| 字段 | 说明 |
|------|------|
| `drill_id` | 如 `evaluation-a3-live-2026-10-30` |
| `environment` | staging / prod-canary |
| `operator` | 执行人 |
| `items.backup_restore_rollback` | #4 备份恢复 + 切回共宿 |
| `items.healthz_protocol` | #1 独立进程 healthz / protocol |

```bash
export AIPLAT_LIVE_DRILL_ID=evaluation-a3-live-YYYYMMDD
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=alice
bash packages/aiplat-evaluation/scripts/a3_record_live_drill.sh
```

**不授权 `process_split_authorized`。**
