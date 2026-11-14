---
doc_type: Reference
---

# Tier A 单符号提案 #11 · `load_judge_calib_defaults`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.load_judge_calib_defaults.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.load_judge_calib_defaults.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F2  
> **依赖**：`evaluate_security_judge_calibration` 已授权；META_EVAL F2 绿  
> **禁区**：≠ L5 declare · ≠ security certification

## 范围

允许 **`load_judge_calib_defaults`** 作为 scoped F2 Tier A 默认阈值加载辅助引用。  
≠ 产品 accuracy_claim；≠ L5；≠ security cert；≠ process_split。

实现：`aiPlat-core/core/apps/eval/service/security_judge_calib.py:61`

```text
ACCEPT load_judge_calib_defaults scoped Tier A gate

REJECT load_judge_calib_defaults
```
