---
doc_type: Reference
---

# Tier A 单符号提案 #5 · `wilson_score_ci`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.wilson_score_ci.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.wilson_score_ci.v0.json)  
> **状态**：`pending_owner_authorize`

## 范围

允许 **`wilson_score_ci`** 作为 scoped F1 Tier A **置信区间辅助**（如 pass_rate Wilson CI）。≠ 产品 accuracy_claim。

实现：`aiPlat-core/core/apps/eval/service/mode_intersection_rank.py:46`

```text
ACCEPT wilson_score_ci scoped Tier A gate

REJECT wilson_score_ci
```
