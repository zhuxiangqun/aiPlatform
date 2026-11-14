---
doc_type: Reference
---

# Phase 3 · Tier B 复核日历（草稿）

> 机器：[`evidence/meta_eval/phase3_b_review_calendar.v0.json`](./evidence/meta_eval/phase3_b_review_calendar.v0.json) · 时点 2026-11-14T21:40:00+08:00
> Tier B n=**165** · **诚实锁**：草稿 ≠ 覆盖完成 · A scoped 19/19 ≠ 全局 Tier A 扩容

## Waves

| bucket | n | cadence | owner_role | suite_hook |
|---|---:|---|---|---|
| `B1_subject_adapters` | 15 | quarterly | eval_owner | **attached** → [`PHASE3_B1_SUITE_ATTACH.md`](./PHASE3_B1_SUITE_ATTACH.md) |
| `B2_smoke` | 26 | monthly | eval_owner | **提案中** → [`PHASE3_B2_SUITE_ATTACH_PROPOSAL.md`](./PHASE3_B2_SUITE_ATTACH_PROPOSAL.md) |
| `B3_regression_profiles` | 66 | monthly | module_owner | pending_suite_attach |
| `B4_eval_facade` | 19 | quarterly | platform | pending_suite_attach |
| `B5_types_errors` | 2 | semi_annual | eval_owner | pending_suite_attach |
| `B6_other` | 37 | semi_annual | eval_owner | pending_suite_attach |

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_review_calendar.py
```

## 关联

- [`PHASE3_PREP.md`](./PHASE3_PREP.md)
- [`PHASE3_COVERAGE_REPORT_SKELETON.md`](./PHASE3_COVERAGE_REPORT_SKELETON.md)
- [`PHASE3_SCOPED_CLOSEOUT.md`](./PHASE3_SCOPED_CLOSEOUT.md)
