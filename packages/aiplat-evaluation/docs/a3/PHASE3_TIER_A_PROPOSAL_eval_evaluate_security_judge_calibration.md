---
doc_type: Reference
---

# Tier A 单符号提案 #13 · `eval_evaluate_security_judge_calibration`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.eval_evaluate_security_judge_calibration.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.eval_evaluate_security_judge_calibration.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F2 · **kind**：facade  
> **依赖**：`evaluate_security_judge_calibration` 已授权  
> **禁区**：≠ L5 declare · ≠ security certification

## 范围

允许 **`eval_evaluate_security_judge_calibration`**（CoreFacade 包装）作为 scoped F2 Tier A 引用。  
包装 `evaluate_security_judge_calibration`；≠ 产品 accuracy_claim；≠ L5；≠ security cert。

实现：`aiPlat-core/core/api/core_facade.py:8095`

```text
ACCEPT eval_evaluate_security_judge_calibration scoped Tier A gate

REJECT eval_evaluate_security_judge_calibration
```
