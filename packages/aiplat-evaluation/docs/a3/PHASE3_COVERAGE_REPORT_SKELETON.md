---
doc_type: Reference
---

# Phase 3 · 覆盖率报表骨架（A/B/C 分列）

> 机器：[`evidence/meta_eval/phase3_coverage_report_skeleton.v0.json`](./evidence/meta_eval/phase3_coverage_report_skeleton.v0.json) · 时点 2026-11-14T21:33:12+08:00
> **禁止**单一「覆盖%」；B/C 的 `with_suite`/`with_gate` 仍为 null（待实测）


| tier | n | with_suite | with_gate | scoped_authorized | exempt | unauthorized_claim |
|---|---:|---:|---:|---:|---:|---|
| A_candidate | 19 | 19 | 19 | 19 | 0 | False |
| B | 165 | None | None | None | 0 | False |
| C | 458 | None | None | None | 0 | False |

## 诚实锁

- `tier_a_expansion_authorized=False`
- `a_candidate_scoped_complete=True`
- `forbid_single_coverage_percent=true`
- A.`with_gate` = 按符号 scoped 账本；**≠** 全局扩容授权

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_coverage_report_refresh.py
```
