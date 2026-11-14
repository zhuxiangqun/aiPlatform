---
doc_type: Reference
---

# Tier A 单符号提案 #4 · `cohen_kappa_binary`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.cohen_kappa_binary.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.cohen_kappa_binary.v0.json)  
> **状态**：`pending_owner_authorize`  
> **依赖**：#1–#3 已接受

---

## 提案范围（若 owner 接受）

允许将 **`cohen_kappa_binary`** 记为 scoped F1 Tier A **度量辅助**（IAA/κ 计算），供门禁引用。

| 允许 | 不允许 |
|---|---|
| 仅本符号作为 F1 度量 helper 授权 | 全局扩容 / 产品 accuracy_claim |
| 与 G2b κ 证据链引用 | 把 κ 本身当成准确率认证 |

实现：`aiPlat-core/core/apps/eval/service/g2c.py:30`

---

## Owner 决策

```text
ACCEPT cohen_kappa_binary scoped Tier A gate

REJECT cohen_kappa_binary
```
