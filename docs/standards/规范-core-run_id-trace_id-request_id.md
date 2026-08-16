---
title: 规范：aiPlat-core Run/Trace/Request 三 ID（企业平台默认）
date: 2026-04-18
scope: aiPlat-platform + aiPlat-core + aiPlat-management（全链路）
status: approved
draft_date: 2026-07-04
approved_date: 2026-08-16
---

## 1. 三个 ID 的分工（必须分离）

| 名称 | 权威生成方 | 格式建议 | 目的 |
|---|---|---|---|
| request_id | platform | `req_<ulid>` | **幂等 + 审计关联**（一次“请求意图”） |
| run_id | core | `run_<ulid>` | **一次执行实例**（有生命周期/事件流/审批） |
| trace_id | core | `trace_<ulid>` 或 uuid | **观测链路**（span/syscalls/links） |

核心原则：
- **request_id ≠ run_id**：重试/转发/回放都围绕 request_id 做幂等；
- **run_id ≠ trace_id**：同一个 run 可能有多段 trace（例如内部重试/子流程），但对外仍是一条 run 记录。

### 1.1 消歧记录（P0-C2，2026-08-16）

| 规范原文 | 代码事实 | 消歧 |
|---|---|---|
| run_id 格式 `run_<ulid>` | pipeline run_id 实际为 `run-<uuid12>`（`core/api/core_facade.py:1868`） | 格式为**建议值**，以代码实现为准（前缀 `run-` + 唯一 ID）；`run_<ulid>` 保留为推荐目标 |
| 未提及 job 调度 | `core/management/job_scheduler.py:179` 使用 `jobrun-<uuid12>` 独立命名空间 | 补充：**job 调度 run_id 与 pipeline run_id 命名空间分离**（`jobrun-` 前缀），不可混用 |

---

## 2. 幂等：request_id → run_id 映射（推荐，未实现）

企业场景中（尤其 app→platform→core），建议由 core 提供一条幂等映射表：

- 表：`request_dedup(tenant_id, request_id, run_id, created_at, status)`
- 规则：
  1) platform 转发给 core 时必须带 `X-AIPLAT-REQUEST-ID`
  2) core 收到请求先查 `(tenant_id, request_id)`：
     - 若存在：直接返回已有 run_id（以及当前 run 状态）
     - 若不存在：生成新的 `run_<ulid>`，写入映射表，再开始执行

> **状态标注（P0-C2）**：`request_dedup` 表当前**未实现**。本节为推荐设计（幂等目标），实现前不得将"已实现"写入文档或 UI 声称。

这样可以保证：
- 上游超时重试不会创建重复 run
- 审计、审批、回放都能以 request_id 聚合

---

## 3. 贯穿字段（落库/事件/审计）

core 在以下记录中都应写入三者（至少 run_id + trace_id + request_id）：
- `run_events`（run_id + trace_id + tenant_id）
- `syscall_events`（run_id + trace_id + tenant_id + target_type/target_id）
- `agent_executions/skill_executions/tool_executions`（run_id + trace_id + tenant_id）
- `approval_requests`（run_id + request_id + tenant_id）
- `audit_logs`（action 的 request_id + run_id + actor）

management 展示层建议以：
1) run_id 作为主对象；
2) trace_id 作为“钻取链接”；
3) request_id 作为“跨系统关联键”（platform/app 的日志也用它聚合）。


---

## 4. 自动触发 run 的产生源（P2-A6/A7，2026-08-16 补充）

`core/harness/execution/event_loop.py` 的 loop scheduler 是自动 run 的产生源之一，新增两种模式：

| 模式 | 触发方式 | run 语义 |
|------|---------|---------|
| `mode=script`（P2-A7） | cron 触发，`params.mode="script"` | **无 run_id**——直接执行 shell/python 脚本（零 LLM），结果经 `result_channel` 投递；不产生 pipeline run 记录 |
| `mode=goal`（P2-A6） | goal 触发，每轮 `_judge_goal_condition` 评估 | 未达成时 `_start_pipeline_from_scene` 产生 pipeline run（`run-<uuid12>`），`iterations_left` 预算内续跑；达成或预算耗尽停止 |

**契约要点**：
- script 模式**不落 run 记录**（无 LLM、无 pipeline 状态机）——观测通过 scheduler 日志（`script trigger ...: OK`）完成
- goal 模式的每次续跑都是**独立 run**（run_id 前缀 `run-`），通过 trigger_id + `iterations_left` 关联重试链，trace_id 由各 run 独立生成
- 两者共享 scheduler 的 `_TRIGGERS_PATH`（`~/.aiplat/loop/triggers.json`）持久化 `last_run` / `iterations_left`

### 4.1 事件源双写（P2-A1，2026-08-17 补充）

`PipelineRunStore` 升级为"状态 + 事件"双写（向后兼容，不迁移现有状态逻辑）：

- **表**：`pipeline_run_events`（append-only：`seq/run_id/event_type/stage_id/payload/created_at`）
- **事件类型**：`stage_started / stage_completed / stage_skipped / stage_paused / stage_failed / hitl_requested / hitl_resolved / run_phase_changed / pipeline_started / pipeline_finished`（引擎回调映射：progress/hitl/finished/failed/cancelled/paused）
- **语义**：run 当前状态仍在 `pipeline_runs`（状态快照），事件日志用于回放/审计/UI 时间线；`seq` 单调递增保证顺序
- **契约**：事件 payload 含 `phase / current_stage_idx / pass_rate`；`run_id` 复用 `run-<uuid12>` 命名空间，与 trace_id 独立
