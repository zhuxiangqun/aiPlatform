---
doc_type: Reference
---

# Tier A 单符号提案 #8 · `build_release_scorecard`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.build_release_scorecard.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.build_release_scorecard.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F4  
> **依赖**：F1 门禁已授权；META_EVAL F4 绿

## 范围

允许 **`build_release_scorecard`** 作为 scoped F4 Tier A 发布记分卡引用。  
未计分轴仍 holdout；≠ 产品 accuracy_claim；≠ process_split。

实现：`aiPlat-core/core/harness/evaluation/release_scorecard.py:42`

```text
ACCEPT build_release_scorecard scoped Tier A gate

REJECT build_release_scorecard
```
