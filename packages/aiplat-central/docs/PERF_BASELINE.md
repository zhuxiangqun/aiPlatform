# aiPlat Central — local performance baseline (D2)

> 本地工程基线，**不是**生产 SLA。

| 检查 | 门槛 | 命令 |
|------|------|------|
| Contract samples | < 5s wall · exit 0 | `python3 reports/five-products/modules/aiplat/contracts/validate_sample.py` |
| D1 smoke | < 30s · exit 0 | `bash packages/aiplat-central/scripts/d1_smoke.sh` |
| Compat + security | gate budgets | `d2_compat_check.sh` · `d2_security_check.sh` |

全五能力复跑：`bash scripts/check_five_products_perf_baseline.sh`  
（可选 smoke：`AIPLAT_PERF_INCLUDE_SMOKE=1`）

生产 PG/HA / 多租户负载须真实预发另测；本文件不授权 cutover。
