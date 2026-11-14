---
doc_type: Reference
---

# Tier A 单符号提案 #18 · `build_g2b_s_dual_review_workflow`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.build_g2b_s_dual_review_workflow.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.build_g2b_s_dual_review_workflow.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F3  
> **禁区**：接受本提案 **≠** `process_split_authorized=true`

## 范围

允许 **`build_g2b_s_dual_review_workflow`** 作为 scoped F3 Tier A 双人复核工作流构建引用。  
≠ process_split 翻转；≠ 产品 accuracy_claim。

实现：`aiPlat-core/core/apps/eval/service/security_cert_prep.py:197`

```text
ACCEPT build_g2b_s_dual_review_workflow scoped Tier A gate

REJECT build_g2b_s_dual_review_workflow
```
