---
doc_type: Archive
---

# Engineering unfreeze — EVAL **P2-1 Context management baseline**

- **decided_at**: `2026-11-06`
- **status**: **Closed** · `EVAL_P2_CONTEXT_CLOSEOUT_2026-11-06.md`（历史链接失效）
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_P2.md`](./ENGINEERING_UNFREEZE_EVAL_P2.md)
- **charter**: [`EVAL_P2_CHARTER_2026-11-06.md`](../../EVAL_P2_CHARTER_2026-11-06.md)
- **protocol**: [`packages/aiplat-evaluation/docs/a3/CONTEXT_V0.md`](../../../../../packages/aiplat-evaluation/docs/a3/CONTEXT_V0.md)
- **depends**: P2-0 calibration closed (`EVAL_P2_CALIBRATION_CLOSEOUT_2026-11-06.md`（历史链接失效）)

## 目标

在本地建立**上下文管理工程基准 v0**：长上下文召回、摘要保真、冲突处理、截断降级。
复用 P2-0 的诚实锁与抽样纪律；**不**冒充生产对话质量，**不**翻 `accuracy_claim`。

## 允许

| 允许 | 说明 |
|---|---|
| 协议 + fixture pack + scorer/runner + gate | `CONTEXT_V0.md` · `context_tasks.v0.json` · `context_mgmt` |
| 确定性 fixture 门禁（可无 LLM） | 工程回归 |
| 证据写入 `docs/a3/drills/` | `accuracy_claim=false` |

## 禁止

| 禁止 | 原因 |
|---|---|
| 用 Session v0/v1 短轮次冒充本基准 | 产品评审已否决 |
| `accuracy_claim=true` / 改 composite 默认 | 超出切片 |
| 持久记忆 / 自学习写回 | 属 P2-2 / P2-3 |
| 生产拆分 / 公网依赖 | P2-4 搁置 |

## 出口

| 项 | 门槛 |
|---|---|
| 四类各 ≥1 fixture 且 gate PASS | recall / summary / conflict / truncation |
| `context_v0_gate.sh` 绿 | claim=false · authorize=false |
| 方法说明落盘 | `CONTEXT_V0.md` |
| closeout 短页 | `EVAL_P2_CONTEXT_CLOSEOUT_*.md`（gate 通过后） |

## 诚实锁

context_mgmt v0 ≠ long-horizon agent cert · ≠ memory Recall@k · ≠ accuracy
