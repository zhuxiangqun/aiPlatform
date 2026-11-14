---
doc_type: Reference
---

# G2b expand 31–100 · 双标状态板

> 机器：[`evidence/meta_eval/g2b_expand_31_100_status.v0.json`](./evidence/meta_eval/g2b_expand_31_100_status.v0.json)  
> 索引：[`G2B_N100.md`](./G2B_N100.md) · 收口：[`G2B_ACCURACY_CLOSEOUT.md`](./G2B_ACCURACY_CLOSEOUT.md)

## 结论

**31–100 双人标注已完成**（非待办）。B4S_PREP 旧文「31–100 待双标」已过期。

| 项 | 值 |
|---|---|
| expand n | **70** / 70 filled（A + B） |
| 全包 n | 100 |
| κ / agreement | 见 `g2b_kappa_aggregate.v1.json` |
| disputed | 8（已裁决进 gold） |
| scoped G2b accuracy claim | **true**（2026-11-13 attestation） |
| 平台 `accuracy_claim` 政策 | **true**（Phase3 AUTHORIZE） |
| security cert / Chart | **false** |

## 证据

- A：`evidence/g2b_annotator_a.labels.v1.json`
- B：`evidence/g2b_annotator_b.labels.v1.json`
- Gold：`evidence/g2b_adjudicated_gold.v1.json`
- Attestation：`evidence/g2b_accuracy_claim_attestation.v1.json`

## 仍禁止

- 用 G2b 替代 security certification  
- 翻 Chart / 宣称生产独立  
- 把 scoped G2b claim 写成「全平台准确率认证」
