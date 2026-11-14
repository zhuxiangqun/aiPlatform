---
doc_type: Reference
---

# META_EVAL F3 状态（G2b / process_split 边界）

> 机器：[`evidence/meta_eval/f3_process_split_boundary_status.v0.json`](./evidence/meta_eval/f3_process_split_boundary_status.v0.json) · 时点 2026-11-14T23:18:36+08:00
> **诚实锁**：`family_green` ≠ `process_split_authorized=true` ≠ Tier A · `accuracy_claim=false`

## 汇总

- green **5/5**
- `family_green`: **true**
- `process_split_authorized`: **false**
- `tier_a_claim_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | boundary_hold | ✅ | a3_split_authorize status: process_split locks hold (doc/status false, chart annotation false, ready_to_authorize=false). |
| `gold_audit` | advisory_present | ✅ | G2b adjudication + scoped attestation present; acknowledgements.not_process_split_authorize=true. |
| `contamination` | advisory_only | ✅ | Inherited F1 advisory; R11 advisory_only. |
| `holdout_isolation` | declared | ✅ | process_split_authorized holdout-from-claim declared until checklist+live. |
| `iaa` | green | ✅ | G2b inter-annotator κ=0.7624 ≥ 0.60; accuracy_claim=false on aggregate. |

## 下一步

1. SPLIT_CHECKLIST #1/#4 仍须 live 签字后才可谈 authorize（本家族绿 ≠ 翻转）
2. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f3_status.py`
3. F2 安全人裁判 / dual-human 仍并行待人（≠ 本家族 IAA）

