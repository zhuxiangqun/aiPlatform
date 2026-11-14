---
doc_type: Reference
---

# META_EVAL F4 状态（Release scorecard）

> 机器：[`evidence/meta_eval/f4_release_scorecard_status.v0.json`](./evidence/meta_eval/f4_release_scorecard_status.v0.json) · 时点 2026-11-14T23:14:18+08:00
> **诚实锁**：`family_green` ≠ Tier A 授权 · `accuracy_claim=false` · `process_split_authorized=false`

## 汇总

- green **5/5**
- `family_green`: **true**
- `tier_a_claim_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | green | ✅ | F1 family_green required before F4 treats judge-linked scorecard claims as calibrated. |
| `gold_audit` | green | ✅ | scorecard_v1_check PASS; product accuracy_claim=false; instruction SHA pins verified. |
| `contamination` | advisory_only | ✅ | Inherited F1 advisory + scorecard SHA gate; R11 advisory_only. |
| `holdout_isolation` | declared | ✅ | Null/unscored scorecard axes are holdout-from-claim (microVM/production). |
| `iaa` | green | ✅ | Scorecard feature-5 dual_human attestation confirmed. |

## 下一步

- F4 绿只表示记分卡诚实门与元评测五项对齐；**禁止**宣称 Tier A 自动扩容
- 下一家族：F2（安全门）或 F3（G2b/process_split）

复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f4_status.py`

