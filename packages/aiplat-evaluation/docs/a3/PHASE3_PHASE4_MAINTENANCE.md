---
doc_type: Reference
---

# Phase3/4 无 staging 维护（触发式）

> 机器：[`evidence/meta_eval/phase3_phase4_maintenance_status.v0.json`](./evidence/meta_eval/phase3_phase4_maintenance_status.v0.json) · 2026-11-15T00:34:34+08:00
> **诚实锁**：维护 ≠ closed_loop · ≠ Chart · ≠ staging live

## 1. G2b 决策表更新 → 重跑摄入

| 项 | 值 |
|---|---|
| 当前表 sha256 | `2a2cf239d3bfa353…` |
| 上次摄入 sha | `2a2cf239d3bfa353…` |
| 需重跑 | **否**（sha_matches_last_ingest） |

```bash
python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --from-g2b-fail-table && python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --close-from-g2b-provisional && python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --verify-pack
```

## 2. Cycle1 到 due 日 → 再抽样

as_of **2026-11-15** · 到期需抽：（无）

| bucket | due | days | sample_due | owner_signoff |
|---|---|---:|:---:|:---:|
| `B1_subject_adapters` | 2027-02-12 | 89 | ☐ | ✅ |
| `B2_smoke` | 2026-12-14 | 29 | ☐ | ✅ |
| `B3_regression_profiles` | 2026-12-14 | 29 | ☐ | ✅ |
| `B4_eval_facade` | 2027-02-12 | 89 | ☐ | ✅ |
| `B5_types_errors` | 2027-05-13 | 179 | ☐ | ✅ |
| `B6_other` | 2027-05-13 | 179 | ☐ | ✅ |

```bash
python3 packages/aiplat-evaluation/scripts/phase3_b_cycle1_sample_rerun.py
```

抽样不清 `owner_signoff`；≠ Tier B coverage complete。

## 复跑本板

```bash
python3 packages/aiplat-evaluation/scripts/phase3_phase4_maintenance_status.py
```
