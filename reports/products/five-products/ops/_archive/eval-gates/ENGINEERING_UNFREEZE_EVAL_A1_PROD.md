---
doc_type: Archive
---

# Engineering unfreeze — EVAL **A1 生产部署签核**（独立轨）

- **decided_at**: `2026-11-06`
- **status**: **Parked** — 产品决定本地签认足够（[`EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md`](../../EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md)）
- **parent plan**: [`EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md`](../../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §3
- **母版**: `EVAL_A1_DEPLOY_SIGNOFF.md`（历史链接失效）
- **本地已签（不可复用）**: `EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md`（历史链接失效）
- **工作稿**: `EVAL_A1_DEPLOY_SIGNOFF_prod_OPEN_2026-11-06.md`（历史链接失效）
- **前阻塞单**: `EVAL_A1_PROD_BLOCKED_NOT_RELEASED_2026-11-05.md`（历史链接失效）

## 目标

在**正式环境**（非 localhost / 非隧道冒充）完成 A1 发布完整性签核：入口 `/eval`、15 tabs、旧 URL 404、CDN/产物、状态文案、三人签。

## 允许

| 允许 | 说明 |
|---|---|
| 预填签认稿、核对源码 TABS、记录构建 SHA | 本轨 |
| 对正式 BASE 执行 curl/浏览器验收 | BASE 提供后 |
| 结论 `pass` / `blocked_not_released` / `fail` | 诚实记录 |

## 禁止

| 禁止 | 原因 |
|---|---|
| 复用本地联调 pass 为生产 | 母版 §7 |
| 隧道 / 本机冒充生产 BASE | 已否决 |
| 环境不可达却勾 pass | 须 `blocked_not_released` |

## 出口

| 项 | 门槛 |
|---|---|
| 正式 BASE（https 主机或已批内网正式 UI） | 非 `localhost` |
| §1–§5 全过 + §6 三人签 | 或诚实 blocked/fail |
| 落盘 `EVAL_A1_DEPLOY_SIGNOFF_<env>_<date>.md` | 更新执行计划状态栏 |

## 诚实锁

A1 生产签核 ≠ process_split · ≠ accuracy_claim · ≠ P2-4 生产治理全过
