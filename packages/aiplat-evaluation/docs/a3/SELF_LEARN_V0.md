# Self-learning resistance baseline v0（P2-3）

> **Unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_SELF_LEARN.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_P2_SELF_LEARN.md)  
> **Honesty**: `accuracy_claim=false` · `writeback_authorized=false`（受 P2-0 校准约束）  
> **Risk input**: [`human_calibration_aggregate.v0.json`](./evidence/human_calibration_aggregate.v0.json) overall disagree_rate=0.2667

## 1. 目的

| kind | 测什么 |
|---|---|
| `before_after` | 受信反馈后目标任务分不降（仅 authorize=true 的夹具分支） |
| `transfer` | 相关任务可迁移；不相关任务不被错误带偏 |
| `forgetting` | 过期/应遗忘规则不再生效；旧好规则不无故崩塌 |
| `bad_feedback` | 恶意/错误反馈被拒绝；策略不变 |
| `audit_rollback` | 每次变更可追溯；rollback 恢复快照 |

## 2. 写回纪律（强制）

| 条件 | 行为 |
|---|---|
| pack / case `writeback_authorized=false`（默认） | `apply` 不得改 live policy（可记 shadow audit） |
| feedback `trusted=false` 或 `malicious=true` | 拒绝 |
| calibration disagree_rate ≥ 0.20 | 门禁要求 `writeback_authorized=false` |

## 3. Runner / Pack

| 项 | 值 |
|---|---|
| Runner | `self_learn` |
| Pack | [`self_learn_tasks.v0.json`](./self_learn_tasks.v0.json) |
| Schema | `eval.scoring.self_learn.v0` |
| Gate | `bash packages/aiplat-evaluation/scripts/self_learn_v0_gate.sh` |

## 4. 非目标

≠ 生产 experience 写回 · ≠ 模型微调 · ≠ process_split · ≠ accuracy
