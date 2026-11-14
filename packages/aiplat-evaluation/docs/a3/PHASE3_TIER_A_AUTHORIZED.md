---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **全局扩容**：`global_tier_a_expansion_authorized=true`（[`PHASE3_GLOBAL_TIER_A_EXPANSION_AUTHORIZE.md`](./PHASE3_GLOBAL_TIER_A_EXPANSION_AUTHORIZE.md)）  
> **仍锁**：`accuracy_claim=false` · `l5_declare_authorized=false` · `security_certification=false` · `process_split_authorized=false`

## 状态

- A_candidate 按符号 scoped：**19/19**  
- 全局 Tier A 扩容：**authorized**（仅此旗标）  
- ≠ 产品准确率认证 / L5 declare / security cert / process_split / 单一覆盖%

## 已授权符号（19）

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

owner：朱向群。

## 下一步（须另授）

```text
AUTHORIZE accuracy_claim
AUTHORIZE l5_declare
AUTHORIZE process_split
CONTINUE phase2_staging_prep
CONTINUE phase3_tier_c_register_only
```
