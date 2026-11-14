---
doc_type: Reference
---

# Phase 3 · B1 suite 挂接提案（Subject adapters）

> 机器：[`evidence/meta_eval/phase3_b1_suite_attach_proposal.v0.json`](./evidence/meta_eval/phase3_b1_suite_attach_proposal.v0.json)  
> **状态**：`pending_owner_authorize` · **≠** 全局 Tier A 扩容 · **≠** 覆盖完成宣称  
> 日历：[`PHASE3_B_REVIEW_CALENDAR.md`](./PHASE3_B_REVIEW_CALENDAR.md) · bucket `B1_subject_adapters`（n=15）

## 范围

为 B1 15 个 SubjectAdapter 符号挂接可复跑 smoke/suite 钩子（`suite_hook` 从 `pending_suite_attach` → 已挂路径）。  
不翻转 `global_tier_a_expansion_authorized`；不宣称单一覆盖%。

## 样本符号

`AgentSubjectAdapter` · `ApiSubjectAdapter` · `CodeReviewSubjectAdapter` · `DatasetSubjectAdapter` · `EvalSubjectAdapter` · `GeneratedAppSubjectAdapter` · `KbSubjectAdapter` · `ModelSubjectAdapter` · …

## Owner

```text
ACCEPT phase3_b_suite_attach B1

REJECT phase3_b_suite_attach B1

AUTHORIZE global_tier_a_expansion
```
