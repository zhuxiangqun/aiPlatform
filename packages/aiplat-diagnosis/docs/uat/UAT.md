# Diagnosis — D3 local UAT (cohost dry-run)

> 本地验收清单；**不是** process_split 生产授权。

| # | 步骤 | 本地命令 / 证据 |
|---|------|----------------|
| 1 | Clean install | `d1_install.sh` |
| 2 | Contracts | `modules/diagnosis/contracts/validate_sample.py` |
| 3 | Upgrade / rollback / backup | `d1_upgrade` · `d1_rollback --runtime` · `d1_backup` |
| 4 | A3 local rehearsal | `a3_local_rehearsal.sh` → 🟨 |
| 5 | Split authorize REFUSE | `a3_split_authorize.sh authorize` |
| 6 | Evidence JSON | `docs/drills/local-diagnosis-d3-uat-*.json` |

一键：`bash packages/aiplat-diagnosis/scripts/d3_local_acceptance.sh`
