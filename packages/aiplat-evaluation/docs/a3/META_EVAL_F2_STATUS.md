---
doc_type: Reference
---

# META_EVAL F2 状态（Security family）

> 机器：[`evidence/meta_eval/f2_security_family_status.v0.json`](./evidence/meta_eval/f2_security_family_status.v0.json) · 时点 2026-11-14T19:10:54+08:00
> **诚实锁**：`family_green` ≠ L5 declare ≠ Tier A · `accuracy_claim=false` · `security_certification=false`

## 汇总

- green **3/5**
- `family_green`: **false**
- `tier_a_claim_authorized`: **false**
- `l5_declare_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | pending_security_human_judge | ❌ | Pending security-specific human judge ratings (F1 prerequisite=met; F1 ≠ F2 security judge). |
| `gold_audit` | advisory_present | ✅ | S1 aggregate present with honesty locks (accuracy_claim=false, not_security_certification=true). |
| `contamination` | advisory_only | ✅ | Inherited F1 advisory; R11 advisory_only. |
| `holdout_isolation` | declared | ✅ | L5 declare / security certification holdout-from-claim declared. |
| `iaa` | pending_security_dual_human | ❌ | F1 G2b IAA must not substitute security dual_human_on_failures. Need security failure dual-human attestation pack. |

## 下一步（仍须人 / 安全专项）

1. 填 `f2_security_judge_pack_pin`：安全题人裁判 + confidence → agreement/κ/ECE
2. 安全失败集 dual-human attestation（≠ F1 G2b IAA）
3. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f2_status.py`

