---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本（按符号）

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **诚实锁**：`global_tier_a_expansion_authorized=false` · `accuracy_claim=false` · `l5_declare_authorized=false` · `security_certification=false` · `process_split_authorized=false`

## 已授权（scoped）

| 符号 | 家族 | 范围 |
|---|---|---|
| `evaluate_judge_calibration_gate` | F1 | 裁判校准门禁 |
| `open_capability_judge_calibration` | F1 | 开票/登记 |
| `judge_calibration_gate_for_ticket` | F1 | 按工单门禁 |
| `cohen_kappa_binary` | F1 | κ/IAA 辅助 |
| `wilson_score_ci` | F1 | Wilson CI 辅助 |
| `eval_judge_calibration_gate` | F1 | CoreFacade 包装 #1 |
| `eval_open_capability_judge_calibration` | F1 | CoreFacade 包装 #2 |
| `build_release_scorecard` | F4 | 发布记分卡（未计分轴 holdout） |
| `build_judge_calib_evidence_pack` | F4 | 证据包构建（≠ security cert） |
| `evaluate_security_judge_calibration` | F2 | 安全裁判校准（≠ L5 / cert） |
| `load_judge_calib_defaults` | F2 | 默认阈值加载（≠ L5 / cert） |
| `evaluate_security_family_gates` | F2 | 安全家族门禁报告（≠ cert） |
| `eval_evaluate_security_judge_calibration` | F2 | CoreFacade 包装（≠ L5 / cert） |
| `eval_load_security_judge_calib_defaults` | F2 | CoreFacade 包装（≠ L5 / cert） |
| `eval_evaluate_security_family_gates` | F2 | CoreFacade 包装（≠ cert） |
| `eval_evaluate_security_severity_l5_gate` | F2 | L5-*gate API* facade（`l5_declare` 仍 false） |

owner：朱向群。F1 7/7 + F4 2/2 + F2 7/7 scoped。下一步进入 **F3**（≠ process_split）。

## 下一步

提案 #17：[`PHASE3_TIER_A_PROPOSAL_assert_t13_process_split_boundary.md`](./PHASE3_TIER_A_PROPOSAL_assert_t13_process_split_boundary.md)
