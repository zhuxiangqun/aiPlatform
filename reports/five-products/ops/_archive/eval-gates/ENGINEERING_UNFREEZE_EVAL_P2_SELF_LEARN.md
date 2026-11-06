# Engineering unfreeze — EVAL **P2-3 Self-learning resistance**

- **decided_at**: `2026-11-06`
- **status**: **Closed** · [`EVAL_P2_SELF_LEARN_CLOSEOUT_2026-11-06.md`](./EVAL_P2_SELF_LEARN_CLOSEOUT_2026-11-06.md)
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_P2.md`](./ENGINEERING_UNFREEZE_EVAL_P2.md)
- **charter**: [`EVAL_P2_CHARTER_2026-11-06.md`](./EVAL_P2_CHARTER_2026-11-06.md)
- **protocol**: [`packages/aiplat-evaluation/docs/a3/SELF_LEARN_V0.md`](../../../packages/aiplat-evaluation/docs/a3/SELF_LEARN_V0.md)
- **depends**: P2-0 calibration closed（disagree_rate 作风险输入；**不**授权写回）

## 目标

本地建立**自学习抗性工程基准 v0**：更新前后、迁移、遗忘/回归、错误反馈抗性、追溯回滚。  
默认 `writeback_authorized=false`（P2-0 校准结论）；**不**改生产自学习路径。

## 允许

| 允许 | 说明 |
|---|---|
| 协议 + fixture + in-process policy 模拟 + gate | `SELF_LEARN_V0.md` · `self_learn_tasks.v0.json` · `self_learn` |
| 引用 P2-0 aggregate 风险字段 | claim=false |

## 禁止

| 禁止 | 原因 |
|---|---|
| 打开生产写回 / 静默改 composite | P2-0 明确禁止 |
| 把「分数上升」当成功唯一条件 | 须含负向用例 |
| process_split / 公网治理 | P2-4 |

## 出口

| 项 | 门槛 |
|---|---|
| 五类各 ≥1 fixture 且 gate PASS | before_after / transfer / forgetting / bad_feedback / audit_rollback |
| `self_learn_v0_gate.sh` 绿 | claim=false · writeback_authorized=false |
| closeout 短页 | `EVAL_P2_SELF_LEARN_CLOSEOUT_*.md` |

## 诚实锁

self_learn v0 ≠ 生产持续学习认证 · ≠ 授权写回 · ≠ accuracy
