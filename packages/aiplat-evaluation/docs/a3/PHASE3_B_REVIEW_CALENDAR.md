---
doc_type: Reference
---

# Phase 3 · Tier B 复核日历

> 机器：[`evidence/meta_eval/phase3_b_review_calendar.v0.json`](./evidence/meta_eval/phase3_b_review_calendar.v0.json) · 2026-11-14T22:56:16+08:00
> Tier B n=**165** · Cycle 1：[`PHASE3_B_REVIEW_CYCLE1.md`](./PHASE3_B_REVIEW_CYCLE1.md)
> **诚实锁**：B1–B6 suite_hook **attached** ≠ 覆盖完成

## Waves

| bucket | n | cadence | owner_role | next_review | suite_hook |
|---|---:|---|---|---|---|
| `B1_subject_adapters` | 15 | quarterly | eval_owner | 2027-02-12 | **attached** |
| `B2_smoke` | 26 | monthly | eval_owner | 2026-12-14 | **attached** |
| `B3_regression_profiles` | 66 | monthly | module_owner | 2026-12-14 | **attached** |
| `B4_eval_facade` | 19 | quarterly | platform | 2027-02-12 | **attached** |
| `B5_types_errors` | 2 | semi_annual | eval_owner | 2027-05-13 | **attached** |
| `B6_other` | 37 | semi_annual | eval_owner | 2027-05-13 | **attached** |

汇总：[`PHASE3_B_SUITE_ATTACH_ROLLUP.md`](./PHASE3_B_SUITE_ATTACH_ROLLUP.md)

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_review_cycle1.py
```
