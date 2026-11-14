---
doc_type: Reference
---

# Tier A 单符号提案 #2 · `open_capability_judge_calibration`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.open_capability_judge_calibration.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.open_capability_judge_calibration.v0.json)  
> **状态**：`pending_owner_authorize`  
> **依赖**：#1 `evaluate_judge_calibration_gate` 已接受

---

## 提案范围（若 owner 接受）

允许将 **`open_capability_judge_calibration`** 记为 scoped F1 Tier A gate（打开/登记裁判校准工单路径）。

| 允许 | 不允许 |
|---|---|
| 仅本符号授权 | 全局扩容 / 产品 accuracy_claim |
| 与 #1 一并构成 F1 开票+门禁引用 | L5 / process_split / 其余符号自动开 |

实现：`aiPlat-core/core/apps/eval/service/capability_p4_gate.py:96`

---

## Owner 决策

```text
ACCEPT open_capability_judge_calibration scoped Tier A gate

REJECT open_capability_judge_calibration
```

---

## 关联

- 账本：[`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md)  
- 扩序：[`PHASE3_TIER_A_EXPAND_ORDER.md`](./PHASE3_TIER_A_EXPAND_ORDER.md)
