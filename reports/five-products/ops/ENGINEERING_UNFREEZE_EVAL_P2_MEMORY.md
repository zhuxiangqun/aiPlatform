# Engineering unfreeze — EVAL **P2-2 Persistent memory (Recall@k)**

- **decided_at**: `2026-11-06`
- **status**: **Closed** · [`EVAL_P2_MEMORY_CLOSEOUT_2026-11-06.md`](./EVAL_P2_MEMORY_CLOSEOUT_2026-11-06.md)
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_P2.md`](./ENGINEERING_UNFREEZE_EVAL_P2.md)
- **charter**: [`EVAL_P2_CHARTER_2026-11-06.md`](./EVAL_P2_CHARTER_2026-11-06.md)
- **protocol**: [`packages/aiplat-evaluation/docs/a3/MEMORY_V0.md`](../../../packages/aiplat-evaluation/docs/a3/MEMORY_V0.md)
- **depends**: P2-0/P2-1 closed

## 目标

本地建立**持久记忆工程基准 v0**：写入、Recall@k、更新/过期、删除后不再召回、租户隔离、污染抵抗。  
使用确定性租户夹具；**不**接生产 MemoryManager 写路径，**不**翻 `accuracy_claim`。

## 允许

| 允许 | 说明 |
|---|---|
| 协议 + fixture + in-process store 模拟 + gate | `MEMORY_V0.md` · `memory_tasks.v0.json` · `memory_persist` |
| 证据写入 `docs/a3/drills/` | claim=false |

## 禁止

| 禁止 | 原因 |
|---|---|
| 直写 core MemoryManager / 生产库 | 切片为评测夹具，非平台接线 |
| 用 Session/context 冒充记忆 | 产品评审已区分 |
| 自学习写回 / process_split | P2-3 / P2-4 |
| `accuracy_claim=true` | 诚实锁 |

## 出口

| 项 | 门槛 |
|---|---|
| 六类各 ≥1 fixture 且 gate PASS | write / recall_at_k / update_expiry / delete / tenant / pollution |
| `memory_v0_gate.sh` 绿 | claim=false · authorize=false |
| closeout 短页 | `EVAL_P2_MEMORY_CLOSEOUT_*.md` |

## 诚实锁

memory_persist v0 ≠ 生产记忆 SLA · ≠ 向量检索认证 · ≠ accuracy
