---
doc_type: Reference
---

# Tier 覆盖矩阵 v0（evaluation-system）

> 计划 §4.5 / §8 · 源：R12 `in_both` · 机器：[`evidence/tier_matrix_v0.json`](./evidence/tier_matrix_v0.json)
> **诚实锁**：`A_candidate` **≠** 已授权 Tier A gate 宣称；须 [`META_EVAL_V0.md`](./META_EVAL_V0.md) 绿灯
> **时点**：2026-11-14T17:34:23+08:00

## 汇总

| Tier | 数量 | 含义 |
|---|---:|---|
| **A_candidate** | 19 | 准确率/证据/安全门/记分卡相关；扩容前须元评测 |
| **B** | 160 | Subject/smoke/pack/方法轨等内部关键路径 |
| **C** | 458 | 其余登记符号（含 Error/helper） |

## A_candidate（摘录）

- `assert_t13_process_split_boundary`
- `build_g2b_s_dual_review_workflow`
- `build_judge_calib_evidence_pack`
- `build_release_scorecard`
- `cohen_kappa_binary`
- `eval_assert_t13_process_split_boundary`
- `eval_evaluate_security_family_gates`
- `eval_evaluate_security_judge_calibration`
- `eval_evaluate_security_severity_l5_gate`
- `eval_judge_calibration_gate`
- `eval_load_security_judge_calib_defaults`
- `eval_open_capability_judge_calibration`
- `evaluate_judge_calibration_gate`
- `evaluate_security_family_gates`
- `evaluate_security_judge_calibration`
- `judge_calibration_gate_for_ticket`
- `load_judge_calib_defaults`
- `open_capability_judge_calibration`
- `wilson_score_ci`

## 下一步

1. 按家族挑 A_candidate 做 META_EVAL 绿灯（非一次全开）→ [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)
2. B 轨挂 suite + 复核日历
3. C 仅登记；禁止挤占 A 名额

## 关联

- R12：[`R12_CAPABILITY_RECONCILIATION.md`](./R12_CAPABILITY_RECONCILIATION.md) · [`R12_TRIAGE_V0.md`](./R12_TRIAGE_V0.md)
- META：[`META_EVAL_V0.md`](./META_EVAL_V0.md) · [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)

