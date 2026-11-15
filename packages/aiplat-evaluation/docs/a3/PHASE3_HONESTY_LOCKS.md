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
| `process_split_policy_authorized` | **true** | [`PHASE3_PROCESS_SPLIT_AUTHORIZE.md`](./PHASE3_PROCESS_SPLIT_AUTHORIZE.md) |
| `process_split_authorized`（运行时） | **false** | Checklist / PREP_STATUS 直至 live authorize |
| `phase4_routing_authorized` | **true** | [`PHASE4_ROUTING_AUTHORIZE.md`](./PHASE4_ROUTING_AUTHORIZE.md) |
| `b_cycle1_owner_signoff_authorized` | **true** | [`PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md`](./PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md) |
| `security_certification` | **false** | — |
| Chart `a3_process_split_authorized` | **false** | 待 staging live（脚手架已开 ≠ live） |
| `production_independent_claim` | **false** | 待 staging closeout |
| `closed_loop_claim` | **false** | Phase4 账本 ≠ 自动闭环 |
| 单一覆盖% | **禁止** | — |

脚手架：[`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md) · unfreeze `draft_blocked`。  
无 staging 可继续：[`PHASE3_PHASE4_MAINTENANCE.md`](./PHASE3_PHASE4_MAINTENANCE.md)（G2b 漂移 / Cycle1 due 抽样）· 其余板已收口 · `closed_loop_claim` 仍 false。
