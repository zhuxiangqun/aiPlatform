---
doc_type: Reference
---

# Phase 3 · Tier B 首轮复核（Cycle 1）

> 机器：[`evidence/meta_eval/phase3_b_review_cycle1.v0.json`](./evidence/meta_eval/phase3_b_review_cycle1.v0.json) · 2026-11-15T00:23:07+08:00
> 授权：[`PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md`](./PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md)
> **诚实锁**：owner_signoff ≠ 覆盖完成 · Chart 仍 false

| bucket | n | due | status | sample_rerun | owner_signoff |
|---|---:|---|---|:---:|:---:|
| `B1_subject_adapters` | 15 | 2027-02-12 | closed | ✅ | ✅ |
| `B2_smoke` | 26 | 2026-12-14 | closed | ✅ | ✅ |
| `B3_regression_profiles` | 66 | 2026-12-14 | closed | ✅ | ✅ |
| `B4_eval_facade` | 19 | 2027-02-12 | closed | ✅ | ✅ |
| `B5_types_errors` | 2 | 2027-05-13 | closed | ✅ | ✅ |
| `B6_other` | 37 | 2027-05-13 | closed | ✅ | ✅ |

## 状态

- Cycle1：`owner_signed`（6/6 buckets）
- `coverage_complete_claim`：**false**
- Chart：**false**

## 复跑（不会清 signoff）

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_cycle1_sample_rerun.py
```
