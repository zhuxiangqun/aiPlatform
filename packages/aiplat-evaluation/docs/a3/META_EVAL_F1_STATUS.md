---
doc_type: Reference
---

# META_EVAL F1 状态（Judge family）

> 机器：[`evidence/meta_eval/f1_judge_family_status.v0.json`](./evidence/meta_eval/f1_judge_family_status.v0.json) · 时点 2026-11-14T18:58:13+08:00
> **诚实锁**：`family_green` 须五项全绿；当前 **≠** Tier A 授权 · `accuracy_claim=false`

## 汇总

- green **5/5**
- `family_green`: **true**
- `tier_a_claim_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | green | ✅ | Judge↔human metrics meet R11 thresholds (report-only). |
| `gold_audit` | green | ✅ | Human re-audit sample scored against R11 gold_audit threshold. |
| `contamination` | advisory_only | ✅ | Scan ran; over-threshold is advisory_only per R11 (over_threshold=True). |
| `holdout_isolation` | declared | ✅ | dev/val/holdout declared; tuning forbidden on holdout; reveal=pre_release_once. Not a score reveal. |
| `iaa` | green | ✅ | IAA only — not judge↔human calibration |

## 下一步

- F1 已 `family_green`：**仍禁止** Tier A 扩容宣称
- 下一家族：F4 / F2 / F3（见 [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)）

复跑状态：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_status.py`

