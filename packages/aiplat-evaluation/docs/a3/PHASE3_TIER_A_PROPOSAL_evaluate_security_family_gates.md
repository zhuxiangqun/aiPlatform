---
doc_type: Reference
---

# Tier A 单符号提案 #12 · `evaluate_security_family_gates`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.evaluate_security_family_gates.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.evaluate_security_family_gates.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F2  
> **依赖**：F2 judge + defaults 已授权；META_EVAL F2 绿  
> **禁区**：≠ security certification · ≠ L5 declare

## 范围

允许 **`evaluate_security_family_gates`** 作为 scoped F2 Tier A 安全家族门禁报告引用。  
≠ 产品 accuracy_claim；≠ L5；≠ security cert；≠ process_split。

实现：`aiPlat-core/core/apps/eval/service/security_family_report.py:428`

```text
ACCEPT evaluate_security_family_gates scoped Tier A gate

REJECT evaluate_security_family_gates
```
