---
doc_type: Archive
---

# G2b n=100 closeout — scoped 确认完成（2026-11-05）

> **人标**：✅ 朱莹 × 朱鸿林（31–100）  
> **仲裁**：✅ 朱向群（新分歧 5 条 + 保留旧 5 条）  
> **κ / accuracy aggregate**：✅ 已写入 evidence  
> **Freeze**：✅ 朱向群确认（`g2b_freeze_record.v1.json`）  
> **Attestation**：✅ **scoped 披露**（`accept_accuracy_claim=false`）

## 数字

| 指标 | 值 | §4 门槛 | 结果 |
|---|---|---|---|
| κ n | 100 | — | — |
| agreement | 0.90 | — | — |
| Cohen κ | 0.7624 | ≥0.60 / 可靠性 ≥0.70 | ✅ |
| model pass-rate vs gold | **0.72**（72/100） | ≥0.80 | ❌ |
| Wilson 95% CI | [0.6251, 0.7986] | 下界 ≥0.70 | ❌ |
| 分歧总数 | 10（01–30 旧 5 + 31–100 新 5） | — | — |

新分歧 gold：`g2b-39=T · 55=F · 62=F · 92=T · 95=F`

**Owner 决定（chat_confirm_scoped）**：仅 scoped 披露；**不翻** `accuracy_claim`。

## 证据路径

- `packages/aiplat-evaluation/docs/a3/evidence/g2b_kappa_aggregate.v1.json`
- `packages/aiplat-evaluation/docs/a3/evidence/g2b_adjudication.v1.json`
- `packages/aiplat-evaluation/docs/a3/evidence/g2b_adjudicated_gold.v1.json`
- `packages/aiplat-evaluation/docs/a3/evidence/g2b_accuracy_aggregate.v1.json`
- freeze：`…/evidence/g2b_freeze_record.v1.json`
- attestation：`…/evidence/g2b_accuracy_claim_attestation.v1.json`

## 仍待（非 G2b claim）

Arena pilot / A1 生产仍按人侧剩余清单。

## 诚实锁

κ ≠ accuracy · claim=false · scoped ≠ 通用准确率 · ≠ process_split · ≠ 安全认证 · 本地 ≠ 生产
