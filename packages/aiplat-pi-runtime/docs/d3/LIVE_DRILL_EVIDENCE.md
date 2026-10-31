# Pi D3 生产类 live 演练证据（运维填写）

> 本地 checksum / SOC file-sink 🟨 **不能**替代本页。填齐后由运维将 `D3_CHECKLIST` 对应项改为 ✅，再 `d3_authorize.sh authorize`。

## 必填

| 字段 | 说明 |
|------|------|
| `drill_id` | 如 `pi-d3-live-2026-10-31` |
| `environment` | staging / prod-canary |
| `operator` | 执行人 |
| `production_signed` | 运维确认后 JSON 置 `true`（脚本默认 `false`） |

## items

| key | 对应 # |
|-----|--------|
| `bundle_integrity` | #3 |
| `ops_surface` | #4 |
| `soc_alert_export` | #5（真实出口，非本地 jsonl） |
| `n1_upgrade_rollback` | #6 |

```bash
export AIPLAT_LIVE_DRILL_ID=pi-d3-live-YYYYMMDD
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=alice
bash packages/aiplat-pi-runtime/scripts/d3_record_live_drill.sh
```

**不授权 `d3_production_authorized`。**
