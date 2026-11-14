---
doc_type: Reference
---

# Tier A 单符号提案 #3 · `judge_calibration_gate_for_ticket`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.judge_calibration_gate_for_ticket.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.judge_calibration_gate_for_ticket.v0.json)  
> **状态**：`pending_owner_authorize`  
> **依赖**：#1+#2 已接受

---

## 提案范围（若 owner 接受）

允许将 **`judge_calibration_gate_for_ticket`** 记为 scoped F1 Tier A gate（按工单跑校准门禁）。

| 允许 | 不允许 |
|---|---|
| 仅本符号授权 | 全局扩容 / 产品 accuracy_claim |
| 与 #1/#2 构成开票→门禁闭环引用 | L5 / process_split / 其余符号自动开 |

实现：`aiPlat-core/core/apps/eval/service/capability_p4_gate.py:161`

---

## Owner 决策

```text
ACCEPT judge_calibration_gate_for_ticket scoped Tier A gate

REJECT judge_calibration_gate_for_ticket
```
