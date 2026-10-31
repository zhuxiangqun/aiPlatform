# Ontology A3 生产类 live 拆分演练证据

> 本地文件/prefix 🟨 **不能**替代。证据齐后运维将 `SPLIT_CHECKLIST` #3/#5（及契约项若需）改为 ✅，再 `a3_split_authorize.sh authorize`。

## 必填

| 字段 | 说明 |
|------|------|
| `drill_id` | 如 `ontology-a3-live-2026-10-30` |
| `environment` | staging / prod-canary |
| `operator` | 执行人 |
| `items.storage_migration` | #3 双写/迁移校验 |
| `items.rollback_cohost` | #5 切回共宿验证 |
| `items.healthz_contract` | #1 独立进程 healthz（若已起） |

```bash
export AIPLAT_LIVE_DRILL_ID=ontology-a3-live-YYYYMMDD
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=alice
bash packages/aiplat-ontology/scripts/a3_record_live_drill.sh
```

**不授权 `process_split_authorized`。**
