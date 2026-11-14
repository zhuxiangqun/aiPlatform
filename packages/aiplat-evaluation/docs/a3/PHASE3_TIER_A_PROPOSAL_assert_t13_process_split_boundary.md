---
doc_type: Reference
---

# Tier A 单符号提案 #17 · `assert_t13_process_split_boundary`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.assert_t13_process_split_boundary.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.assert_t13_process_split_boundary.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F3  
> **禁区**：接受本提案 **≠** `process_split_authorized=true`

## 范围

允许 **`assert_t13_process_split_boundary`** 作为 scoped F3 Tier A **边界断言** 引用。  
仅授权可调用该 assert；**不**翻转 process_split、不声明产品 accuracy。

实现：`aiPlat-core/core/apps/eval/service/security_t13_allowlist.py:261`

```text
ACCEPT assert_t13_process_split_boundary scoped Tier A gate

REJECT assert_t13_process_split_boundary
```
