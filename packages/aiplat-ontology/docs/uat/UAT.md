---
doc_type: Reference
---

# Ontology — D3 local UAT (cohost dry-run)

> **包级证据（E2）**：本文件只描述本包本地基线/UAT，不是跨包通用模板；跨包比较需以各包数值和证据为准。


> 本地验收清单；**不是** process_split 生产授权。

| # | 步骤 | 本地命令 / 证据 |
|---|------|----------------|
| 1 | Clean install | `d1_install.sh` |
| 2 | Contracts | `modules/ontology/contracts/validate_sample.py` |
| 3 | Upgrade / rollback / backup | `d1_upgrade` · `d1_rollback --runtime` · `d1_backup` |
| 4 | A3 local rehearsal | `a3_local_rehearsal.sh` → 🟨 |
| 5 | Split authorize REFUSE | `a3_split_authorize.sh authorize` |
| 6 | Evidence JSON | `docs/drills/local-ontology-d3-uat-*.json` |

一键：`bash packages/aiplat-ontology/scripts/d3_local_acceptance.sh`
