---
doc_type: Reference
---

# Phase 3 · 诚实锁总表

> 机器：[`evidence/meta_eval/phase3_honesty_locks.v0.json`](./evidence/meta_eval/phase3_honesty_locks.v0.json) · 2026-11-14T23:40:00+08:00  
> owner：朱向群

| 旗标 | 值 | 授权事件 |
|---|---|---|
| `global_tier_a_expansion_authorized` | **true** | [`PHASE3_GLOBAL_TIER_A_EXPANSION_AUTHORIZE.md`](./PHASE3_GLOBAL_TIER_A_EXPANSION_AUTHORIZE.md) |
| `accuracy_claim` | **true** | [`PHASE3_ACCURACY_CLAIM_AUTHORIZE.md`](./PHASE3_ACCURACY_CLAIM_AUTHORIZE.md) |
| `l5_declare_authorized` | **true** | [`PHASE3_L5_DECLARE_AUTHORIZE.md`](./PHASE3_L5_DECLARE_AUTHORIZE.md) |
| `process_split_authorized` | **true**（政策） | [`PHASE3_PROCESS_SPLIT_AUTHORIZE.md`](./PHASE3_PROCESS_SPLIT_AUTHORIZE.md) |
| `phase4_routing_authorized` | **true** | [`PHASE4_ROUTING_AUTHORIZE.md`](./PHASE4_ROUTING_AUTHORIZE.md) |
| `security_certification` | **false** | — |
| Chart `a3_process_split_authorized` | **false** | 待 staging live（脚手架已开 ≠ live） |
| `production_independent_claim` | **false** | 待 staging closeout |
| `closed_loop_claim` | **false** | Phase4 账本 ≠ 自动闭环 |
| 单一覆盖% | **禁止** | — |

脚手架：[`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md) · unfreeze `draft_blocked`。  
无 staging 可继续：[`G2B_EXPAND_31_100_STATUS.md`](./G2B_EXPAND_31_100_STATUS.md) · [`PHASE3_TIER_A_GOLD_GATE_LEDGER.md`](./PHASE3_TIER_A_GOLD_GATE_LEDGER.md) · [`PHASE3_B_REVIEW_CYCLE1.md`](./PHASE3_B_REVIEW_CYCLE1.md) · [`PHASE4_PREP.md`](./PHASE4_PREP.md)（routing AUTHORIZE · G2b→disposition 可摄入 · `closed_loop_claim` 仍 false）。
