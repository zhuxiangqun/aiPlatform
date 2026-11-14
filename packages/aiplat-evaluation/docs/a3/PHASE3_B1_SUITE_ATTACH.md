---
doc_type: Reference
---

# Phase 3 · B1 suite 挂接账本

> 机器：[`evidence/meta_eval/phase3_b1_suite_attach.v0.json`](./evidence/meta_eval/phase3_b1_suite_attach.v0.json)  
> owner ACCEPT · 全局扩容仍 false

## 挂接规则

| 符号类 | suite_hook |
|---|---|
| 13 个 typed Subject | `run_<kind>_capability_smoke`（`*_capability_bank.py`） |
| `AgentSubjectAdapter` | `agent_smoke_profile`（`capability_case_bank.py`） |
| `EvalSubjectAdapter` | Protocol + registry（**partial**；无专用 smoke） |

完整逐符号 `impl_ref` 见机器 JSON。复跑 smoke 走既有 bank 函数；本页不宣称 B 轨覆盖完成。
