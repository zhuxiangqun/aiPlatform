---
doc_type: Reference
---

# META_EVAL F1 状态（Judge family）

> 机器：[`evidence/meta_eval/f1_judge_family_status.v0.json`](./evidence/meta_eval/f1_judge_family_status.v0.json) · 时点 2026-11-14T17:51:52+08:00
> **诚实锁**：`family_green` 须五项全绿；当前 **≠** Tier A 授权 · `accuracy_claim=false`

## 汇总

- green **1/5**
- `family_green`: **false**
- `tier_a_claim_authorized`: **false**

## 五项

| 检查 | 状态 | green | 说明 |
|---|---|:---:|---|
| `judge_calibration` | open | ❌ | No frozen judge↔human ratings pack with ECE in evidence/meta_eval/. G2b IAA must not be reused as judge calibration green. Next: open_capability_judge_calibration + dual ratings → evaluate_judge_calibration_gate + ECE artifact. |
| `gold_audit` | advisory_present | ❌ | Adjudication artifact present; sample error-rate ≤5% not yet measured for META_EVAL F1 — keep blocked. |
| `contamination` | not_run | ❌ | No contamination overlap report for F1 family; R11 over-threshold=advisory_only |
| `holdout_isolation` | declared_local | ❌ | Freeze confirmed for G2b pack; META_EVAL still requires explicit dev/val/holdout split declaration for Tier A family — not green. |
| `iaa` | green | ✅ | IAA only — not judge↔human calibration |

## 下一步（开 judge 绿灯）

1. 固定人标 pack 指纹 + seed（禁止边调边改）
2. `open_capability_judge_calibration` → 双人/人机 ratings
3. `evaluate_judge_calibration_gate` + κ/ECE 写入 `evidence/meta_eval/`
4. 补 gold 抽样错误率、contamination 报告、holdout 三分声明

复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_status.py`

