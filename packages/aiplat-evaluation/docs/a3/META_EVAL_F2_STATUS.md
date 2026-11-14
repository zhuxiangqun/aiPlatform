---
doc_type: Reference
---

# META_EVAL F2 状态（Security family）

> 机器：[`evidence/meta_eval/f2_security_family_status.v0.json`](./evidence/meta_eval/f2_security_family_status.v0.json) · 时点 2026-11-14T19:48:35+08:00
> **诚实锁**：`family_green` ≠ L5 declare ≠ Tier A · `accuracy_claim=false` · `security_certification=false`

## 汇总

- green **4/5**
- `family_green`: **false**
- `tier_a_claim_authorized`: **false**
- `l5_declare_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | green | ✅ | Security human judge metrics meet R11. |
| `gold_audit` | advisory_present | ✅ | S1 aggregate present with honesty locks (accuracy_claim=false, not_security_certification=true). |
| `contamination` | advisory_only | ✅ | Inherited F1 advisory; R11 advisory_only. |
| `holdout_isolation` | declared | ✅ | L5 declare / security certification holdout-from-claim declared. |
| `iaa` | pending_security_dual_human | ❌ | F1 G2b IAA must not substitute security dual_human_on_failures. Fill f2_security_dual_human.worksheet then set status=attested green=true. |

## 下一步（仍须人 / 安全专项）

1. 填写说明：[`META_EVAL_F2_HUMAN_FILL.md`](./META_EVAL_F2_HUMAN_FILL.md)
2. 填安全裁判 worksheet → `meta_eval_f2_prep.py --score`
3. 填 dual-human worksheet → `status=attested` `green=true`
4. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f2_status.py`

