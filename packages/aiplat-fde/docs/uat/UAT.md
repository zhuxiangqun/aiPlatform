# FDE Field — D3 local UAT (dry-run)

> 本地验收清单；**不是**客户签字 / 生产 D3。

| # | 步骤 | 本地命令 / 证据 |
|---|------|----------------|
| 1 | Clean install | `d1_install.sh --smoke` |
| 2 | Contracts | `modules/fde/contracts/validate_sample.py` |
| 3 | Upgrade N-1 | `d1_upgrade.sh` |
| 4 | Runtime rollback | `d1_rollback.sh --runtime` |
| 5 | Backup | `d1_backup.sh` |
| 6 | Smoke | `d1_smoke.sh` |
| 7 | Evidence JSON | `docs/drills/local-fde-d3-uat-*.json` |

一键：`bash packages/aiplat-fde/scripts/d3_local_acceptance.sh`
