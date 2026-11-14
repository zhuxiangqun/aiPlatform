---
doc_type: Reference
---

# Tier A 单符号提案 #10 · `evaluate_security_judge_calibration`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.evaluate_security_judge_calibration.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.evaluate_security_judge_calibration.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F2  
> **依赖**：F1 + F4 已授权；META_EVAL F2 绿  
> **禁区**：≠ L5 declare · ≠ security certification

## 范围

允许 **`evaluate_security_judge_calibration`** 作为 scoped F2 Tier A 安全裁判校准引用。  
≠ 产品 accuracy_claim；≠ L5；≠ security cert；≠ process_split。

实现：`aiPlat-core/core/apps/eval/service/security_judge_calib.py:321`

```text
ACCEPT evaluate_security_judge_calibration scoped Tier A gate

REJECT evaluate_security_judge_calibration
```
