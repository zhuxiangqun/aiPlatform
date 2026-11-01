# FDE Field — local performance baseline (D2)

> 本地工程基线，**不是**生产 SLA。

| 检查 | 门槛 | 命令 |
|------|------|------|
| Contract samples | < 5s wall · exit 0 | `python3 reports/five-products/modules/fde/contracts/validate_sample.py` |
| D1 smoke | < 30s · exit 0 | `bash packages/aiplat-fde/scripts/d1_smoke.sh` |

全五能力复跑：`bash scripts/check_five_products_perf_baseline.sh`

现场生产负载 / compose 长驻另批；不改 Field Accepted 范围。
