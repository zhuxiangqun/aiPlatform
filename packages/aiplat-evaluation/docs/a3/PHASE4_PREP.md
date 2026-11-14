---
doc_type: Reference
---

# Phase 4 预备（修复闭环 · routing 已授权）

> 机器：[`evidence/meta_eval/phase4_repair_loop_prep_board.v0.json`](./evidence/meta_eval/phase4_repair_loop_prep_board.v0.json) · 2026-11-14T23:43:40+08:00
> 账本：[`evidence/meta_eval/phase4_disposition_ledger.v0.json`](./evidence/meta_eval/phase4_disposition_ledger.v0.json)
> 路由：[`config/phase4_routing.v0.json`](./config/phase4_routing.v0.json)
> 计划 §10 · **诚实锁**：账本 ≠ 「自动改进已闭环」· Chart 仍 false

## 闸门

| 项 | 状态 |
|---|---|
| `build_failure_taxonomy` import | ✅ |
| G2b fail decision table | ✅ |
| `compare_eval_reports` import | ✅ |
| routing 配置文件 | ✅ |
| `phase4_routing_authorized` | ✅ |
| disposition 账本写路径 | ✅ |
| 复评 pack 指纹 stub | ✅ |
| runtime router 接线 | ❌ |
| closed_loop_claim | **false** |

## 路由（配置 · 未 runtime 强制）

| category | route_to | owner SLA | disposition SLA |
|---|---|---:|---:|
| `environment` | infra_ops | 24h | 72h |
| `data` | fixture_gold_owner | 24h | 72h |
| `implementation` | module_owner | 24h | 72h |
| `stale_assertion` | eval_owner_plus_product | 24h | 72h |
| `product_defect` | product_owner | 24h | 72h |
| `eval_defect` | eval_owner_meta | 24h | 72h |
| `unknown` | eval_owner | 24h | 72h |

## 下一步

1. Human disposition + close tickets (phase4_disposition_ledger.py --close)
2. Same-pack reeval after disposition (fingerprint)
3. Runtime auto-dispatch remains off

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --demo
python3 packages/aiplat-evaluation/scripts/phase4_repair_loop_prep.py
```
