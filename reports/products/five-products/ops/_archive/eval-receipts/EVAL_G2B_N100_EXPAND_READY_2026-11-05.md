---
doc_type: Archive
---

# G2b 31–100 — 出卷 → scoped 收口完成（2026-11-05）

> **工程**：✅ n=100 pack · model 100/100 · κ · 仲裁 · accuracy closeout · freeze
> **人侧**：✅ 朱莹 / 朱鸿林 盲标 · ✅ 朱向群 仲裁 · ✅ freeze 确认 · ✅ scoped attestation
> **`accuracy_claim`**：**false**（§4 门槛未达；owner 确认 scoped）
> **Protocol**：已 SIGNED · Holdout A · [SIGNED 留存](../../EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md)
> **收口页**：[EVAL_G2B_N100_CLOSEOUT_2026-11-05.md](./EVAL_G2B_N100_CLOSEOUT_2026-11-05.md)

## Pack 位置（gitignored）

```
packages/aiplat-evaluation/docs/a3/human_pack/20261105T132500Z-n100/
  g2b_31_100_朱莹.csv / g2b_31_100_朱鸿林.csv   ← 已填回
  g2b_annotator_a.filled.json / g2b_annotator_b.filled.json
  …
```

统计：`dual_human_n=70` · `kappa n=100 agreement=0.90 κ=0.7624` · `pass_rate=0.72` · `accuracy_claim=false`

## Freeze / Attestation（已确认）

| 项 | 状态 |
|---|---|
| Freeze owner | **朱向群** ✅ |
| Model/prompt/config hash | ✅ `docs/a3/evidence/g2b_freeze_record.v1.json` |
| Attestation | ✅ scoped · `accept_accuracy_claim=false` · `g2b_accuracy_claim_attestation.v1.json` |
| 渠道 | `chat_confirm_scoped` |

## 标注员

| 卷 | 人 |
|---|---|
| Annotator A | 朱莹 ✅ |
| Annotator B | 朱鸿林 ✅ |
| 仲裁 / freeze / attestation | 朱向群 ✅ |
