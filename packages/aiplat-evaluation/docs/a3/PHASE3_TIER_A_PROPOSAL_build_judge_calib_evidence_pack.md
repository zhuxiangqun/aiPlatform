---
doc_type: Reference
---

# Tier A 单符号提案 #9 · `build_judge_calib_evidence_pack`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.build_judge_calib_evidence_pack.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.build_judge_calib_evidence_pack.v0.json)  
> **状态**：`pending_owner_authorize` · **家族**：F4  
> **依赖**：F1 门禁 + `build_release_scorecard` 已授权；META_EVAL F4 绿

## 范围

允许 **`build_judge_calib_evidence_pack`** 作为 scoped F4 Tier A 证据包构建引用。  
未计分轴仍 holdout；≠ 产品 accuracy_claim；≠ security cert / L5 / process_split。

实现：`aiPlat-core/core/apps/eval/service/security_cert_prep.py:140`

```text
ACCEPT build_judge_calib_evidence_pack scoped Tier A gate

REJECT build_judge_calib_evidence_pack
```
