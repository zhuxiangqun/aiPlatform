---
doc_type: Reference
---

# META_EVAL 汇总状态

> 机器：[`evidence/meta_eval/meta_eval_aggregate_status.v0.json`](./evidence/meta_eval/meta_eval_aggregate_status.v0.json) · 时点 2026-11-14T19:58:20+08:00
> **诚实锁**：`meta_eval_families_green` ≠ Tier A 扩容授权 · ≠ L5 · ≠ process_split · `accuracy_claim=false`

## 汇总

- families_green **4/4**
- `meta_eval_families_green`: **true**
- `tier_a_expansion_authorized`: **false**

## 家族

| 家族 | green | family_green | 状态页 |
|---|:---:|:---:|---|
| F1 Judge calibration | 5/5 | ✅ | [`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md) |
| F2 Security family gates | 5/5 | ✅ | [`META_EVAL_F2_STATUS.md`](./META_EVAL_F2_STATUS.md) |
| F3 G2b / process_split boundary | 5/5 | ✅ | [`META_EVAL_F3_STATUS.md`](./META_EVAL_F3_STATUS.md) |
| F4 Release scorecard | 5/5 | ✅ | [`META_EVAL_F4_STATUS.md`](./META_EVAL_F4_STATUS.md) |

## 下一步

1. Phase 3 预备：见 [`PHASE3_PREP.md`](./PHASE3_PREP.md)（仍须 owner 授权才扩 Tier A gate）
2. Phase 2 authorize 仍独立：[`PHASE2_PREP.md`](./PHASE2_PREP.md) / SPLIT_CHECKLIST
3. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_aggregate_status.py`

