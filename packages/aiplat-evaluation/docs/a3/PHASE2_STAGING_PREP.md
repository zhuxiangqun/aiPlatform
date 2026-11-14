---
doc_type: Reference
---

# Phase 2 · Staging 预备板

> 机器：[`evidence/meta_eval/phase2_staging_prep_board.v0.json`](./evidence/meta_eval/phase2_staging_prep_board.v0.json)  
> 父页：[`PHASE2_PREP.md`](./PHASE2_PREP.md) · [`B4S_PREP.md`](./B4S_PREP.md) · [`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md)

## 当前

| 项 | 状态 |
|---|---|
| 政策 `process_split_authorized` | **true**（owner 覆盖） |
| 本机 B4-S rehearsal | ✅ |
| B4-S staging 脚手架 / unfreeze 草稿 | ✅ `draft_blocked` |
| 独立 staging host | ❌ |
| Chart runtime split | **false** |
| 生产独立宣称 | **禁止** |

## 下一步

1. Owner 确认独立 staging host（非开发本机）  
2. 将 [`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md) 从 `draft_blocked` → `active`  
3. JWKS + 对象存储 + PITR live 演练（`production_signed`）  
4. 仅此后：`bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize` 翻 Chart
