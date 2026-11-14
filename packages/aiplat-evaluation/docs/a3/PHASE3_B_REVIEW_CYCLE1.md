---
doc_type: Reference
---

# Phase 3 · Tier B 首轮复核（Cycle 1）

> 机器：[`evidence/meta_eval/phase3_b_review_cycle1.v0.json`](./evidence/meta_eval/phase3_b_review_cycle1.v0.json) · 2026-11-15T00:40:54+08:00
> 开板：`2026-11-14` · sample_rerun **6/6**
> **诚实锁**：owner_signoff 已 AUTHORIZE · ≠ 覆盖完成 · Chart 仍 false

| bucket | n | due | status | sample_rerun | owner_signoff |
|---|---:|---|---|:---:|:---:|
| `B1_subject_adapters` | 15 | 2027-02-12 | closed | ✅ | ✅ |
| `B2_smoke` | 26 | 2026-12-14 | closed | ✅ | ✅ |
| `B3_regression_profiles` | 66 | 2026-12-14 | closed | ✅ | ✅ |
| `B4_eval_facade` | 19 | 2027-02-12 | closed | ✅ | ✅ |
| `B5_types_errors` | 2 | 2027-05-13 | closed | ✅ | ✅ |
| `B6_other` | 37 | 2027-05-13 | closed | ✅ | ✅ |

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_cycle1_sample_rerun.py
```

owner_signoff 已 AUTHORIZE；本脚本只刷新抽样，不清 signoff。
