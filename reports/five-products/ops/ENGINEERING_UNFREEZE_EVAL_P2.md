# Engineering unfreeze — EVAL **P2** 立项开篇

- **decided_at**: `2026-11-06`
- **status**: **Open (P2-4 only)** · P2-0..P2-3 **已收口** · P2-4 生产治理仍搁置（无公网）
- **parent plan**: [`EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md`](./EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §5
- **P1b human closeout**: [`EVAL_P1B_HUMAN_TRACK_CLOSEOUT_2026-11-05.md`](./EVAL_P1B_HUMAN_TRACK_CLOSEOUT_2026-11-05.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)

## 背景

P0/P1b 人侧与报告轨已收口。A1 **生产**仍 `blocked_not_released`（无公网）。按计划 P2 **不阻塞** P0/P1，须独立立项：先定 owner / 风险 / 数据 / 预算，再排期。

## P2 范围（计划原文五条）

| # | 主题 | 公网依赖 | 建议次序 |
|---|---|---|---|
| 1 | 上下文管理（长上下文召回、摘要保真、冲突、截断降级） | 低（可本地） | 2 |
| 2 | 持久记忆（写入、Recall@k、更新/过期、删除、租户隔离、污染抵抗） | 低–中 | 3 |
| 3 | 自学习（更新前后、迁移、遗忘、错误反馈抗性、追溯回滚） | 中 | 4（依赖校准） |
| 4 | **Evaluator calibration**（人工抽样复核误报/漏报/漂移） | **低** | **1（首切片）** |
| 5 | 生产治理（动态 tenant、retention、cohost SLO/灾备、staging/B4-S/B5/B6） | **高** | 搁置至有正式环境 |

## 本文件允许 / 禁止

| 允许 | 说明 |
|---|---|
| 写 P2 charter、首切片协议、数据清单、owner 表 | 本文 + [`EVAL_P2_CHARTER_2026-11-06.md`](./EVAL_P2_CHARTER_2026-11-06.md) |
| 启动 **P2-0 Evaluator calibration** 工程预备（本地） | 另开 `ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md` 后方可改生产默认 |
| 保持 `accuracy_claim=false` · `process_split_authorized=false` | 诚实锁 |

| 禁止 | 原因 |
|---|---|
| 无 charter 直接大改记忆/自学习默认路径 | 计划 §5：先 owner/风险/预算 |
| 用隧道/本机冒充生产治理门 C | A1 生产仍 blocked |
| 把 P2 插入并净增 P1 未完成承诺 | 等量替换规则；P1b 已 close |
| 静默翻 `accuracy_claim` | 须独立 attestation + 门槛 |

## 出口（kickoff）

| 项 | 门槛 |
|---|---|
| Charter 落盘 | owner 候选、风险、数据、预算粗估齐 |
| 首切片选定 | 默认 **P2-0 calibration**（见 charter） |
| 产品负责人确认 | 微信/口头确认本 unfreeze + 首切片 |
| 工程开工 | 另开 calibration 专用 unfreeze 后才改代码默认 |

## 诚实锁

P2 kickoff ≠ 能力已交付 · ≠ 生产授权 · ≠ accuracy claim · 无公网 ≠ 可做本地校准预备
