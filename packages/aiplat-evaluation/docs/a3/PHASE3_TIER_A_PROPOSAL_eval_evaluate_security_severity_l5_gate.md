---
doc_type: Reference
---

# Tier A 单符号提案 #16 · `eval_evaluate_security_severity_l5_gate`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.eval_evaluate_security_severity_l5_gate.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.eval_evaluate_security_severity_l5_gate.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F2 · **kind**：facade  
> **禁区**：接受本提案 **≠** `l5_declare_authorized=true` · ≠ security certification

## 范围

允许 **`eval_evaluate_security_severity_l5_gate`**（CoreFacade 包装）作为 scoped F2 Tier A **门禁评估 API** 引用。  
仅授权「可调用该 gate 评估入口」；**不**翻转 L5 宣告、不认证安全合格、不声明产品 accuracy。

实现：`aiPlat-core/core/api/core_facade.py:8255`

```text
ACCEPT eval_evaluate_security_severity_l5_gate scoped Tier A gate

REJECT eval_evaluate_security_severity_l5_gate
```
