---
doc_type: Reference
---

# Tier A 单符号提案 #19 · `eval_assert_t13_process_split_boundary`（末）

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.eval_assert_t13_process_split_boundary.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.eval_assert_t13_process_split_boundary.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F3 · **kind**：facade · **A_candidate 末项**  
> **禁区**：接受本提案 **≠** `process_split_authorized` · **≠** `global_tier_a_expansion_authorized`

## 范围

允许 **`eval_assert_t13_process_split_boundary`**（CoreFacade 包装）作为 scoped F3 Tier A 引用。  
包装 `assert_t13_process_split_boundary`。19/19 全部 scoped 授权后，**全局扩容旗标仍保持 false**，除非另有明确授权。

实现：`aiPlat-core/core/api/core_facade.py:8349`

```text
ACCEPT eval_assert_t13_process_split_boundary scoped Tier A gate

REJECT eval_assert_t13_process_split_boundary
```
