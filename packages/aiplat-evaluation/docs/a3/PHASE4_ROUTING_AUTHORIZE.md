---
doc_type: Reference
---

# AUTHORIZE phase4_routing

> 机器：[`evidence/meta_eval/phase4_routing_authorize.v0.json`](./evidence/meta_eval/phase4_routing_authorize.v0.json)  
> **状态**：`authorized`（朱向群 · `AUTHORIZE phase4_routing`） · 2026-11-14T23:40:00+08:00  
> 路由表：[`config/phase4_routing.v0.json`](./config/phase4_routing.v0.json)

## 翻转

| 项 | 值 |
|---|---|
| 政策 `phase4_routing_authorized` | **true** |
| disposition 账本写路径 | ✅ |
| demo 关单 + 同指纹 stub | ✅（演练） |
| G2b fail 表 → taxonomy 摄入 | 工程路径（`--from-g2b-fail-table`） |
| runtime auto-dispatch | **仍 false** |
| `closed_loop_claim` | **仍 false** |
| Chart `a3_process_split_authorized` | **仍 false** |
| `security_certification` | **仍 false** |

## 已接受路由

| category | route_to | owner SLA | disposition SLA |
|---|---|---:|---:|
| `environment` | infra_ops | 24h | 72h |
| `data` | fixture_gold_owner | 24h | 72h |
| `implementation` | module_owner | 24h | 72h |
| `stale_assertion` | eval_owner_plus_product | 24h | 72h |
| `product_defect` | product_owner | 24h | 72h |
| `eval_defect` | eval_owner_meta | 24h | 72h |
| `unknown` | eval_owner | 24h | 72h |

预备板：[`PHASE4_PREP.md`](./PHASE4_PREP.md)
