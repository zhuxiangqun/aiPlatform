---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本（按符号）

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **诚实锁**：`global_tier_a_expansion_authorized=false` · `accuracy_claim=false` · `l5_declare_authorized=false` · `security_certification=false`

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

owner：朱向群。F1 7/7 + F4 2/2 + F2 2/7 scoped。≠ 产品准确率认证 / L5 / process_split。

## 下一步

提案 #12：[`PHASE3_TIER_A_PROPOSAL_evaluate_security_family_gates.md`](./PHASE3_TIER_A_PROPOSAL_evaluate_security_family_gates.md)
