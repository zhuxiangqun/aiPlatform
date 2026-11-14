---
doc_type: Reference
---

# Phase 3 · B5 suite 挂接提案（types / errors）

> 机器：[`evidence/meta_eval/phase3_b5_suite_attach_proposal.v0.json`](./evidence/meta_eval/phase3_b5_suite_attach_proposal.v0.json)  
> **状态**：`pending_owner_authorize` · bucket `B5_types_errors`（n=2）  
> **依赖**：B1–B4 已挂接 · **≠** 全局 Tier A 扩容

## 范围

为 `ModeAwareExamError` · `SuiteProfileExamError` 登记类型/错误入口（importable 符号）。  
不翻转全局扩容；不宣称单一覆盖%。

```text
ACCEPT phase3_b_suite_attach B5

REJECT phase3_b_suite_attach B5
```
