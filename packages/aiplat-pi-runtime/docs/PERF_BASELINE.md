# Pi Thin — local performance baseline (D2)

> 本地工程基线，**不是**生产 SLA。

| 检查 | 门槛 | 命令 |
|------|------|------|
| D1 smoke / contracts | < 30s wall · exit 0 | `bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh` |
| D2 admin pack | file checks only | `bash packages/aiplat-pi-runtime/scripts/d2_admin_check.sh` |

全五能力复跑：`bash scripts/check_five_products_perf_baseline.sh`

Edge 生产 SOC / N-1 延迟须 live 另测；不授权 `d3_production`。
