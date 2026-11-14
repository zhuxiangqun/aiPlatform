---
doc_type: Reference
---

# META_EVAL F1 状态（Judge family）

> 机器：[`evidence/meta_eval/f1_judge_family_status.v0.json`](./evidence/meta_eval/f1_judge_family_status.v0.json) · 时点 2026-11-14T17:57:19+08:00
> **诚实锁**：`family_green` 须五项全绿；当前 **≠** Tier A 授权 · `accuracy_claim=false`

## 汇总

- green **3/5**
- `family_green`: **false**
- `tier_a_claim_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | pending_ratings | ❌ | Pack pinned; ratings/ECE missing — not green. Do not reuse G2b IAA as judge calibration. |
| `gold_audit` | pending_human_reaudit | ❌ | Seeded sample_n=20 ready; fill reaudit_* then recompute sample_error_rate. |
| `contamination` | advisory_only | ✅ | Scan ran; over-threshold is advisory_only per R11 (over_threshold=True). |
| `holdout_isolation` | declared | ✅ | dev/val/holdout declared; tuning forbidden on holdout; reveal=pre_release_once. Not a score reveal. |
| `iaa` | green | ✅ | IAA only — not judge↔human calibration |

## 下一步（仍须人）

1. 填 `f1_judge_pack_pin` ratings → agreement/κ/ECE
2. 填 `f1_gold_audit_sample` 的 `reaudit_*` → `sample_error_rate`
3. prep（可复跑）：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_prep.py`

复跑状态：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_status.py`

