---
doc_type: Reference
---

# Tier A 单符号提案 #1 · `evaluate_judge_calibration_gate`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.evaluate_judge_calibration_gate.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.evaluate_judge_calibration_gate.v0.json)  
> **状态**：`accepted`（owner 朱向群 · ACCEPT scoped Tier A gate）  
> **诚实锁**：仅本符号 · 产品 `accuracy_claim=false` · 全局扩容 false

---

## 授权结果

| 字段 | 值 |
|---|---|
| `tier_a_gate_authorized`（本符号） | **true** |
| `global_tier_a_expansion_authorized` | **false** |
| `accuracy_claim` / `claim_eligible` | **false** |
| `report_only` | **仍 true**（代码诚实锁） |

账本：[`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md)

---

## 检查单（结案）

| # | 项 | 结果 |
|---|---|---|
| 1 | 在 A_candidate | ✅ |
| 2 | META F1 绿 | ✅ |
| 3 | 实现 `capability_p4_gate.py:33` | ✅ |
| 4 | 人裁判证据 | ✅ |
| 5 | owner ACCEPT | ✅ 朱向群 |

---

## 下一案

#2 [`PHASE3_TIER_A_PROPOSAL_open_capability_judge_calibration.md`](./PHASE3_TIER_A_PROPOSAL_open_capability_judge_calibration.md)
