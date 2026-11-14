---
doc_type: Reference
---

# Phase 3 · Tier B 首轮复核（Cycle 1）

> 机器：[`evidence/meta_eval/phase3_b_review_cycle1.v0.json`](./evidence/meta_eval/phase3_b_review_cycle1.v0.json) · 2026-11-14T22:56:16+08:00
> 开板：`2026-11-14` · 父日历：[`PHASE3_B_REVIEW_CALENDAR.md`](./PHASE3_B_REVIEW_CALENDAR.md)
> **诚实锁**：suite attached ≠ 覆盖完成 · Chart 仍 false

| bucket | n | cadence | due | status | sample_rerun | owner_signoff |
|---|---:|---|---|---|:---:|:---:|
| `B1_subject_adapters` | 15 | quarterly | 2027-02-12 | open | ☐ | ☐ |
| `B2_smoke` | 26 | monthly | 2026-12-14 | open | ☐ | ☐ |
| `B3_regression_profiles` | 66 | monthly | 2026-12-14 | open | ☐ | ☐ |
| `B4_eval_facade` | 19 | quarterly | 2027-02-12 | open | ☐ | ☐ |
| `B5_types_errors` | 2 | semi_annual | 2027-05-13 | open | ☐ | ☐ |
| `B6_other` | 37 | semi_annual | 2027-05-13 | open | ☐ | ☐ |

## Owner 动作

1. 按 due 日前对该 bucket **抽样复跑** suite（记入 sample_rerun）
2. 消化 `gap_symbols`（若有）
3. owner_signoff 后把该 wave `status` → `closed`

## 复跑生成

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_review_cycle1.py
```
