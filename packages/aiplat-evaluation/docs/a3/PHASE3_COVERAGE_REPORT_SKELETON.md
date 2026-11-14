---
doc_type: Reference
---

# Phase 3 · 覆盖率报表骨架（A/B/C 分列）

> 机器：[`evidence/meta_eval/phase3_coverage_report_skeleton.v0.json`](./evidence/meta_eval/phase3_coverage_report_skeleton.v0.json) · 时点 2026-11-14T21:57:00+08:00
> **禁止**单一「覆盖%」；B.`with_suite` = suite_hook 挂接计数（≠ 覆盖完成）

| tier | n | with_suite | with_gate | scoped_authorized | exempt | unauthorized_claim |
|---|---:|---:|---:|---:|---:|---|
| A_candidate | 19 | 19 | 19 | 19 | 0 | False |
| B | 165 | 165 | None | None | 0 | False |
| C | 458 | None | None | None | 0 | False |

## 诚实锁

- `tier_a_expansion_authorized=false`
- `tier_b_coverage_complete_claim=false`
- `b_suite_attach_waves_complete=true`（钩子挂接齐 ≠ 覆盖完成）
- `forbid_single_coverage_percent=true`

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_coverage_report_refresh.py
```
