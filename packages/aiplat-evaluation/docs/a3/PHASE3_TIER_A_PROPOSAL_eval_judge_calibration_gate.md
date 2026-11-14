---
doc_type: Reference
---

# Tier A 单符号提案 #6 · `eval_judge_calibration_gate`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.eval_judge_calibration_gate.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.eval_judge_calibration_gate.v0.json)  
> **状态**：`pending_owner_authorize` · **kind**：facade_wrapper  
> **包装**：已授权的 `evaluate_judge_calibration_gate`

## 范围

允许 CoreFacade 导出 **`eval_judge_calibration_gate`** 作为与 #1 同 scope 的 Tier A 引用入口。≠ 新宣称面；≠ accuracy_claim。

实现：`aiPlat-core/core/api/core_facade.py:10670`

```text
ACCEPT eval_judge_calibration_gate scoped Tier A gate

REJECT eval_judge_calibration_gate
```
