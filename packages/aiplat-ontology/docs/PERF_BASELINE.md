# Ontology — local performance baseline (D2)

> 本地工程基线，**不是**生产 SLA。

| 检查 | 门槛 | 命令 |
|------|------|------|
| Contract samples | < 5s wall · exit 0 | `python3 reports/five-products/modules/ontology/contracts/validate_sample.py` |
| D1 smoke | < 30s · exit 0 | `bash packages/aiplat-ontology/scripts/d1_smoke.sh` |

记录于 `d2_local_closeout` 证据 JSON（`perf_contract_seconds`）。  
全五能力复跑：`bash scripts/check_five_products_perf_baseline.sh`  
生产负载/延迟须真实预发另测。
