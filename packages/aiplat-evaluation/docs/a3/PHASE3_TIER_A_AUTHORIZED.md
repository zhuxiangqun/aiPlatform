---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本（按符号）

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **诚实锁**：`global_tier_a_expansion_authorized=false` · `accuracy_claim=false` · `l5_declare_authorized=false` · `security_certification=false` · `process_split_authorized=false`

## 状态

**A_candidate 按符号 scoped 授权：19/19 完成**  
**≠** 全局 Tier A 扩容授权 · **≠** 产品准确率认证 · **≠** L5 declare · **≠** security cert · **≠** process_split

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
| `assert_t13_process_split_boundary` | F3 | 边界断言（`process_split` 仍 false） |
| `build_g2b_s_dual_review_workflow` | F3 | 双人复核工作流（≠ process_split） |
| `eval_assert_t13_process_split_boundary` | F3 | CoreFacade 包装（≠ process_split） |

owner：朱向群。扩序见 [`PHASE3_TIER_A_EXPAND_ORDER.md`](./PHASE3_TIER_A_EXPAND_ORDER.md)。

## 下一步（非自动）

若要翻转 `global_tier_a_expansion_authorized` / `accuracy_claim` / `l5_declare` / `process_split`，须 **单独、显式** owner 授权——本账本完成不构成该授权。
