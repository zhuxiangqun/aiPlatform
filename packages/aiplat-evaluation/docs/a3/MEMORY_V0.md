---
doc_type: Reference
---

# Persistent memory baseline v0（P2-2）

> **Unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_MEMORY.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_P2_MEMORY.md)  
> **Honesty**: `accuracy_claim=false` · ≠ context_mgmt · ≠ 生产 MemoryManager 认证

## 1. 目的

| kind | 测什么 |
|---|---|
| `write_precision` | 写入后可按 query 命中目标 id |
| `recall_at_k` | 相关记忆进入 top-k |
| `update_expiry` | 更新文本生效；expired 不再召回 |
| `delete_no_recall` | 删除后 top-k 不含该 id |
| `tenant_isolation` | 跨 tenant 不可召回 |
| `pollution_resistance` | 污染/错误条目不挤掉干净事实 |

## 2. Runner / Pack

| 项 | 值 |
|---|---|
| Runner | `memory_persist` |
| Pack | [`memory_tasks.v0.json`](./memory_tasks.v0.json) |
| Schema | `eval.scoring.memory_persist.v0` |
| Gate | `bash packages/aiplat-evaluation/scripts/memory_v0_gate.sh` |

夹具内 `ops` 驱动 in-process store（write/update/delete/expire）；召回为 token-overlap 排序 + tenant/status 过滤。≠ 向量库 / ≠ 生产接线。

## 3. 验收

- 六类齐；整包 `memory_pass=true`；`accuracy_claim=false`
- 禁止把本门禁写成「记忆准确率」或生产 SLA

## 4. 非目标

≠ 自学习写回 · ≠ 跨进程持久化认证 · ≠ process_split · ≠ 公网
