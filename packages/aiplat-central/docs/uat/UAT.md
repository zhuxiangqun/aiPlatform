---
doc_type: Reference
---

# aiPlat Central — D3 local UAT (Thin dry-run)

> **包级证据（E2）**：本文件只描述本包本地基线/UAT，不是跨包通用模板；跨包比较需以各包数值和证据为准。


> 本地验收清单；**不是** PG/HA cutover 生产授权。

| # | 步骤 | 本地命令 / 证据 |
|---|------|----------------|
| 1 | A2 / compat / security | `a2_version_check` · `d2_compat` · `d2_security` |
| 2 | Contracts | `modules/aiplat/contracts/validate_sample.py` |
| 3 | Install / N-1 / backup | `d1_install` · `d1_upgrade` · `d1_rollback --runtime` · `d1_backup` |
| 4 | PG/HA local rehearsal | `pg_ha_local_rehearsal.sh` |
| 5 | Cutover authorize REFUSE | `pg_ha_cutover_authorize.sh authorize` |
| 6 | Evidence JSON | `docs/drills/local-aiplat-d3-uat-*.json` |

一键：`bash packages/aiplat-central/scripts/d3_local_acceptance.sh`
