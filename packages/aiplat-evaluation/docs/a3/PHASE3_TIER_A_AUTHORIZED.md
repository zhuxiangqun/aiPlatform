---
doc_type: Reference
---

# Phase 3 · Tier A 已授权符号账本（按符号）

> 机器：[`evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json`](./evidence/meta_eval/phase3_tier_a_authorized_symbols.v0.json)  
> **诚实锁**：`global_tier_a_expansion_authorized=false` · `accuracy_claim=false` · 本表 ≠ 一次全开

## 已授权（scoped）

| 符号 | 家族 | owner | 范围 |
|---|---|---|---|
| `evaluate_judge_calibration_gate` | F1 | 朱向群 | F1 裁判校准门禁 |
| `open_capability_judge_calibration` | F1 | 朱向群 | F1 开票/登记 |
| `judge_calibration_gate_for_ticket` | F1 | 朱向群 | F1 按工单跑门禁 |

## 含义

上表三者构成 F1 **开票 → 门禁 → 工单门禁** 的 scoped Tier A 引用集。  
**不可**据此宣称产品准确率认证、L5、process_split、或其余 A_candidate 已授权。

## 下一步

提案 #4：[`PHASE3_TIER_A_PROPOSAL_cohen_kappa_binary.md`](./PHASE3_TIER_A_PROPOSAL_cohen_kappa_binary.md)
