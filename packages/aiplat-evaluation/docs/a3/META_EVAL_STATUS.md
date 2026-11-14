---
doc_type: Reference
---

# META_EVAL 汇总状态

> 机器：[`evidence/meta_eval/meta_eval_aggregate_status.v0.json`](./evidence/meta_eval/meta_eval_aggregate_status.v0.json) · 时点 2026-11-14T23:18:36+08:00
> **诚实锁**：`meta_eval_families_green` ≠ Chart flip · ≠ security cert · 政策旗标见 [`PHASE3_HONESTY_LOCKS.md`](./PHASE3_HONESTY_LOCKS.md)

## 汇总

- families_green **4/4**
- `meta_eval_families_green`: **true**
- `tier_a_expansion_authorized`: **true**（locks）
- `accuracy_claim`: **true**（locks）
- Chart runtime split: **false**

## 家族

| 家族 | green | family_green | 状态页 |
|---|:---:|:---:|---|
| F1 Judge calibration | 5/5 | ✅ | [`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md) |
| F2 Security family gates | 5/5 | ✅ | [`META_EVAL_F2_STATUS.md`](./META_EVAL_F2_STATUS.md) |
| F3 G2b / process_split boundary | 5/5 | ✅ | [`META_EVAL_F3_STATUS.md`](./META_EVAL_F3_STATUS.md) |
| F4 Release scorecard | 5/5 | ✅ | [`META_EVAL_F4_STATUS.md`](./META_EVAL_F4_STATUS.md) |

## 下一步

1. Phase 3：[`PHASE3_PREP.md`](./PHASE3_PREP.md) · Phase 4 预备：[`PHASE4_PREP.md`](./PHASE4_PREP.md)
2. Phase 2 Chart/runtime：[`PHASE2_PREP.md`](./PHASE2_PREP.md) / SPLIT_CHECKLIST
3. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_aggregate_status.py`

