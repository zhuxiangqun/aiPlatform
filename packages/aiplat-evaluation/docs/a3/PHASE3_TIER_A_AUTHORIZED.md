---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本（按符号）

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **诚实锁**：`global_tier_a_expansion_authorized=false` · `accuracy_claim=false` · 本表 ≠ 一次全开

## 已授权（scoped）

| 符号 | 家族 | owner | 范围 |
|---|---|---|---|
| `evaluate_judge_calibration_gate` | F1 | 朱向群 | scoped F1 judge calibration gate；`report_only` 仍在 |
| `open_capability_judge_calibration` | F1 | 朱向群 | scoped F1 开票/登记路径；依赖 #1 |

## 含义

- 可在文档/门禁矩阵中引用上表符号为 **F1 Tier A gate（scoped）**  
- **不可**据此宣称产品准确率认证、L5、process_split、或其余 A_candidate 已授权

## 下一步

提案 #3：[`PHASE3_TIER_A_PROPOSAL_judge_calibration_gate_for_ticket.md`](./PHASE3_TIER_A_PROPOSAL_judge_calibration_gate_for_ticket.md)
