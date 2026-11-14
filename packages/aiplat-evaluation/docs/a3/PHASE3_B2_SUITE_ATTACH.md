---
doc_type: Reference
---

# Phase 3 · B2 suite 挂接账本

> 机器：[`evidence/meta_eval/phase3_b2_suite_attach.v0.json`](./evidence/meta_eval/phase3_b2_suite_attach.v0.json)  
> owner ACCEPT · n=**26** · gaps=**0** · 全局扩容仍 false

## 挂接规则

| 层 | 符号模式 | suite_hook |
|---|---|---|
| impl | `run_*_capability_smoke` | `*_capability_bank.py` |
| facade | `eval_run_*_capability_smoke` | `core_facade.py` |

逐符号 `impl_ref` 见机器 JSON。≠ B 轨覆盖完成宣称。
