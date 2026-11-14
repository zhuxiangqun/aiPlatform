---
doc_type: Reference
---

# META_EVAL 家族清单 v0（A_candidate）

> 源：[`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md) · 协议：[`META_EVAL_V0.md`](./META_EVAL_V0.md) · 阈值：[`R11_META_EVAL_THRESHOLDS.md`](./R11_META_EVAL_THRESHOLDS.md)  
> **诚实锁**：本表是执行清单，**不是** Tier A gate 授权；任一家未绿 → 禁止对该家族新增 Tier A 宣称  
> `accuracy_claim=false` · `process_split_authorized=false`

---

## 用法

1. 一次只开一家（禁止 19 条一次全绿宣称）。  
2. 每家按 META_EVAL 五项勾：judge / gold / contamination / holdout / IAA。  
3. 证据落 `docs/a3/evidence/meta_eval/`（F1–F4：[`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md) · [`META_EVAL_F2_STATUS.md`](./META_EVAL_F2_STATUS.md) · [`META_EVAL_F3_STATUS.md`](./META_EVAL_F3_STATUS.md) · [`META_EVAL_F4_STATUS.md`](./META_EVAL_F4_STATUS.md)）。  
4. 改阈值须 R11 重签 + SHA 日志。

---

## 家族

| ID | 家族 | 代表符号（摘录） | META_EVAL 五项 | Tier A 宣称 |
|---|---|---|---|---|
| F1 | Judge calibration | `evaluate_judge_calibration_gate` · `open_capability_judge_calibration` · `cohen_kappa_binary` · `wilson_score_ci` | **green 5/5**（[`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md)；≠ Tier A 授权） | **blocked**（家族绿 ≠ 扩容授权） |
| F2 | Security family gates | `evaluate_security_family_gates` · `evaluate_security_judge_calibration` · `evaluate_security_severity_l5_gate` | **green 5/5**（[`META_EVAL_F2_STATUS.md`](./META_EVAL_F2_STATUS.md)；≠ L5 declare ≠ security cert） | **blocked**（家族绿 ≠ 扩容/认证授权） |
| F3 | G2b / process_split 边界 | `build_g2b_s_dual_review_workflow` · `assert_t13_process_split_boundary` | **green 5/5**（[`META_EVAL_F3_STATUS.md`](./META_EVAL_F3_STATUS.md)；≠ 翻转 `process_split_authorized`） | **blocked**（家族绿 ≠ authorize） |
| F4 | Release scorecard | `build_release_scorecard` · `build_judge_calib_evidence_pack` | **green 5/5**（[`META_EVAL_F4_STATUS.md`](./META_EVAL_F4_STATUS.md)；依赖 F1 + scorecard_v1_check） | **blocked**（≠扩容授权） |

机器侧完整 `A_candidate` 列表见 [`evidence/tier_matrix_v0.json`](./evidence/tier_matrix_v0.json)。

---

## 建议开工序

```text
F1（尺子）→ F4（记分卡接线）→ F2（安全门）→ F3（G2b/拆分边界）
```

未跑 F1 前，禁止把任一 judge 结果写成 Tier A 硬门禁。F1/F4 绿仍禁止 Tier A 扩容宣称。

---

## 当前状态

| 字段 | 值 |
|---|---|
| recorded | 2026-11-14 |
| families_green | 4 / 4（汇总：[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)；仍 ≠ Tier A 扩容授权） |
| tier_a_expansion_authorized | **false**（Phase 3 预备：[`PHASE3_PREP.md`](./PHASE3_PREP.md)） |
