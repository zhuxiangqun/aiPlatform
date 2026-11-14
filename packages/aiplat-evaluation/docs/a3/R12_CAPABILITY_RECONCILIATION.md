---
doc_type: Reference
---

# R12 · 能力对账结果（tranche-1：evaluation-system）

> 分诊：[`R12_TRIAGE_V0.md`](./R12_TRIAGE_V0.md) · 时点 2026-11-14T17:34:23+08:00
> 复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`

## 汇总

| 指标 | 数量 |
|---|---:|
| registry 符号 | 638 |
| 两边均有 | 637 |
| 差异合计 | 259 |
| open | 73 |
| exempt | 1 |
| downgraded | 53 |
| out_of_tranche | 132 |

## 分诊类别

| 类别 | 数量 |
|---|---:|
| H2 | 1 |
| H3 | 53 |
| H5 | 73 |
| H6 | 132 |

H2/H4 豁免到期：**2027-02-14**。 H1_candidate 已清零（见白名单）。 H5 open ≠ Tier A 扩容；见 [`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md)。

