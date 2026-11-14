---
doc_type: Reference
---

# Tier 覆盖矩阵 v0（evaluation-system）

> 计划 §4.5 / §8 · 源：R12 `in_both` · 机器：[`evidence/tier_matrix_v0.json`](./evidence/tier_matrix_v0.json)
> **诚实锁**：`A_candidate` **≠** 已授权 Tier A gate 宣称；META_EVAL 家族绿见 [`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)
> **时点**：2026-11-14T19:58:20+08:00 · R12 H5 open=**0** · `meta_eval_families_green`=**true**（≠ 扩容授权）

## 汇总

| Tier | 数量 | 含义 |
|---|---:|---|
| **A_candidate** | 19 | 准确率/证据/安全门/记分卡相关；扩容前须元评测 |
| **B** | 165 | Subject/smoke/pack/方法轨等内部关键路径 |
| **C** | 458 | 其余登记符号（含 Error/helper） |

## META_EVAL 前置

- `meta_eval_families_green`: **true**（F1–F4）
- `tier_a_expansion_authorized`: **false**

## 下一步

1. META_EVAL 已绿 → 进入 [`PHASE3_PREP.md`](./PHASE3_PREP.md) 首波 A_candidate 工程预备（禁一次全开）
2. B 轨挂 suite + 复核日历
3. C 仅登记；禁止挤占 A 名额

## 关联

- R12：[`R12_CAPABILITY_RECONCILIATION.md`](./R12_CAPABILITY_RECONCILIATION.md)
- META：[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md) · [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)

