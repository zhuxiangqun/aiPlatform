# EVAL P2-2 — Persistent memory v0 closeout（2026-11-06）

- **status**: **PASS（工程 fixture 门）** · `accuracy_claim=false`
- **unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_MEMORY.md`](./ENGINEERING_UNFREEZE_EVAL_P2_MEMORY.md)
- **protocol**: [`MEMORY_V0.md`](../../../packages/aiplat-evaluation/docs/a3/MEMORY_V0.md)
- **pack**: [`memory_tasks.v0.json`](../../../packages/aiplat-evaluation/docs/a3/memory_tasks.v0.json)
- **gate**: `bash packages/aiplat-evaluation/scripts/memory_v0_gate.sh`

## 范围交付

| 项 | 状态 |
|---|---|
| 六类 fixture（各 ≥2） | ✅ write / recall_at_k / update_expiry / delete / tenant / pollution |
| in-process store + token-overlap Recall@k | ✅（零重叠不垫 top-k） |
| `memory_persist` runner + 测试 4/4 | ✅ |
| gate PASS · authorize=false | ✅ |

## 诚实锁

≠ 生产 MemoryManager SLA · ≠ 向量检索认证 · ≠ context_mgmt · ≠ 自学习写回 · ≠ accuracy

## 下一步

P2-3 自学习抗性（依赖 P2-0 校准风险输入）；P2-4 生产治理仍搁置（无公网）。
