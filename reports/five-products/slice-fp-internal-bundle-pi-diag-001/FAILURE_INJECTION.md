# 故障注入（WP4）

| # | 用例 | 状态 | 证据 |
|---|------|------|------|
| 1 | 伪造/空身份 → 拒绝 | **通过** | `test_require_auth_rejects_missing_and_invalid_key` + `test_auth_gate_on_offline_evaluate_endpoint`（401/403） |
| 2 | 坏 Bundle / 无 manifest → 导出失败 | **通过** | `test_export_rejects_missing_manifest` |
| 3 | 诊断缺 Pi 证据 → unknown | **通过** | `test_evidence_unknown_without_pi` |
| 4 | 离线超 TTL / denied_ops → deny | **通过** | `test_offline_ttl_exceeded_denies` + `test_offline_denied_ops_blocks_heal`；结果快照 `RUNLOG/fault_injection_results.json` |

路径级负向用例：**4/4 已有可重复证据**（单测 + offline evaluator API）。
