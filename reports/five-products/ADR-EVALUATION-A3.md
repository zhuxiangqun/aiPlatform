# ADR — Evaluation A3（评测服务进程/存储独立）

- **状态**：**Accepted（有条件）** · 2026-10-30  
- **草案**：[`ADR-DRAFT-evaluation-a3.md`](./ADR-DRAFT-evaluation-a3.md)（保留对照）  
- **联签**：架构 × 业务 · 用户指令「联签 A3」· 2026-10-30  
- **前置**：Evaluation D1 Thin 共宿（`packages/aiplat-evaluation` · `eval.protocol.v0`）

> **诚实性**：聊天联签 ≠ 生产硬门齐；`cutover_authorized` / `process_split_authorized` / `d3_production_authorized` 未全 ✅ 前禁止生产宣称。

## 决策（有条件）

1. **批准** Evaluation 独立进程 + 评测库（任务/轨迹/报告）的产品化路径。  
2. 控制面经 `eval.protocol.v0` 与 `/api/core/eval/healthz` 消费。  
3. apps/eval HTTP 可迁至独立服务挂载；签收/证据仍不越权进 FDE 真源。  
4. **拆分条件（硬门）**：[`SPLIT_CHECKLIST.md`](../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md) 未全部 ✅ 之前，**禁止** `process_split_authorized=true`，默认仍共宿 D1。  
5. 本地 SQLite 备份/回滚（🟨）**不等于** live 演练绿。

## 非目标

- 不替代 FDE 验收真源  
- 不承诺「所有程序」评测  
- 不批 compose 长驻以外的全拆 / 当日无条件拆分  

## 接受门槛

| # | 门槛 | 证据 |
|---|------|------|
| 1 | `eval.protocol.v0` + healthz | unit + D1 smoke（🟨） |
| 2 | Chart / DB 迁移骨架 | `packages/aiplat-evaluation/chart/` |
| 3 | 控制面经 API | `a3_prep_check` 零 harness 直导 |
| 4 | 备份/回滚演练 | local 🟨；live 仍须 |
| 5 | 联签 | 本文 Accepted（有条件） |

## 备选（未采纳）

| 备选 | 原因 |
|------|------|
| 永久仅共宿 | 无法独立扩缩与保留策略 |
| 无条件当日拆分 | live 演练未齐 |

## 回滚

停 Eval 独立进程；流量切回 platform `apps/eval` 共宿路径。

## 签署

架构 × 业务 · 2026-10-30 · **Accepted（有条件）** · **生产进程拆分仍须 SPLIT_CHECKLIST 全 ✅**
