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

### 4.2 事件折叠派生（P2-A1 第二阶段，2026-08-17 补充）

- `PipelineRunStore.replay_run_events(run_id)`：从 `pipeline_run_events` 折叠出 run 状态快照（`phase / current_stage_idx / pass_rate / stages_visited / last_terminal_event`），`derived=True` 标记事件源视图
- `pipeline_state` API 响应附加 `event_derived` 字段（审计交叉验证；状态快照仍为快速路径）
- 终态事件（`pipeline_finished/failed/cancelled/paused`）携带最终 progress；`pipeline_hitl` 映射为 `review` 状态

### 4.3 读取路径事件源交叉验证（P2-A1 第三阶段，2026-08-17 补充）

- `get_full_state_from_run_id` 响应附加：
  - `event_derived`：事件折叠视图（复用 `replay_run_events`）
  - `state_event_consistent`：状态快照 phase 与事件折叠 phase 一致性标志
- 用途：检测状态/事件漂移（跨 worker 不一致、崩溃恢复后偏差）；状态快照仍为快速路径，事件视图为审计交叉验证

### 4.4 事件回放读取契约 + 观察事件缓冲（2026-08-18 补充）

- **读取端点**：`GET /runs/{run_id}/events?after_seq=N&limit=M`（`runs.py:list_run_events`，经 `execution_store.runs_mixin.list_run_events`）——返回 `{items, after_seq, last_seq}`，`items[]` 含 `seq / type / payload / trace_id / tenant_id / created_at`；`after_seq` 增量拉取用于轮询/追尾
- **回放 UI**：前端 `RunEventTimeline` 组件（Builder 运行历史内联时间线，seq/type/payload 展开查看）消费同一端点，不新增业务读取路径
- **观察缓冲**：`api/routers/observation.py` 的 `_diag_buffers`（per-run_id 诊断事件缓冲）有界化——`_DIAG_TTL=60s` + `_MAX_DIAG_RUNS=256`，每次 `store_diag_event` 清扫过期/超额条目；缓冲仅用于 SSE 首段回放，权威事件源是 `run_events` 表
- **事件源权威**：所有回放/时间线 UI 的最终一致来源是 `run_events` / `pipeline_run_events` 表；内存缓冲（observation / read_cache 等）仅作临时加速，不构成第二条业务真相

### 4.5 运行时缓存有界化契约（2026-08-18 补充）

- **原则**：`run_events` / DB 是唯一权威真相；所有内存缓存（`model_injection._FAILURE_TRACKER` / `_model_overrides`、`context_service` 索引、`credential_pool._pools`、`plugins._slot_archives`、`sql_ontology._translators`）均为临时加速，**必须带上限**（`_MAX_*`）或 TTL，禁止无限增长
- **约束**：新增内存缓存时须声明 `_MAX_*` 上限或 TTL 清扫；键空间来自客户端输入（HTTP 参数 / session_id / provider）时必须校验或设上限
- **落地记录（2026-08-18 二轮）**：`skill_routing._skill_weights`（`_MAX_SKILL_WEIGHTS=512`）、`evolution._latest_predictions`（`_MAX_PREDICTIONS=256`）、`base_model_adapter._model_cache`（`_MAX_MODEL_CACHE=16`）补上限；守卫 §83a 豁免机制从文件级改为**变量名级**（仅 `_REGISTRY/_DEFAULTS/_MAP` 等命名本身豁免，运行时 dict 如 `_running_pipelines` 不再误豁免）
- **落地记录（2026-08-18 三轮）**：`api/routers/diagnostics.py` 将 `_check_security` 注册进 HealthCheckRegistry（模块名 `security`，Severity.HIGH）——诊断体系补全；能力登记 frontmatter `total_capabilities` 与统计表口径统一（verify_capability_consistency.py 增加 frontmatter 校验，--fix 同步双口径）
- **落地记录（2026-08-18 四轮）**：`harness/meta/meta_agent.py` 新增数据驱动 `MetaAgent`（`get_meta_agent().analyze(days)`）——EvolutionEngine meta_analysis step 此前引用不存在的符号导致每次返回 error；本实现基于 execution_store 失败信号 + capability_health_report 聚合，不引入 LLM 依赖。`rule_golden_sample.py --verify` 接入 architecture-guard.yml CI（P0-C7：守卫规则必须有真实命中）
- **落地记录（2026-08-18 五轮）**：`pipeline_engine.py` P2-A4 拆分 Phase 1——自愈策略 13 方法（`_meta_optimize`/`_dispatch_strategy`/`_strategy_*` 等）迁移至 `pipeline_healing.py`（`PipelineHealingMixin`，主类继承）。纯结构迁移，运行语义不变；方法定位路径变化（registry/verify-l4-claims/pyramid/whitepaper_refs 已同步）。
- **落地记录（2026-08-18 六轮）**：P2-A4 拆分 Phase 2——状态持久化 6 方法（`_snapshot`/`_merge_state`/`_load_checkpoints_from_disk`/`_output_root`/`_persist_files`/`_summarize_artifact`）迁移至 `pipeline_state.py`（`PipelineStateMixin`）。主类继承链 `PipelineEngine(PipelineStateMixin, PipelineHealingMixin)`。
- **落地记录（2026-08-18 七轮）**：P2-A4 拆分 Phase 3——prompt 构建 8 方法迁 `pipeline_prompt.py`（`PipelinePromptMixin`），测试评估 6 方法迁 `pipeline_eval.py`（`PipelineEvalMixin`）。主类继承链 `PipelineEngine(PipelineEvalMixin, PipelinePromptMixin, PipelineStateMixin, PipelineHealingMixin)`。
- **落地记录（2026-08-18 八轮）**：P2-A4 拆分 Phase 4（收官）——stage dispatch/exec 8 方法（`_dispatch_execute`/`_infer_profile_from_stage`/`_calibrate_profile_from_history`/`_apply_capability_profile`/`_build_handler_params`/`_exec_isolated_stage`/`_exec_stage`/`_evaluate_stage_health`）迁 `pipeline_stage.py`（`PipelineStageMixin`）。主类继承链 `PipelineEngine(PipelineStageMixin, PipelineEvalMixin, PipelinePromptMixin, PipelineStateMixin, PipelineHealingMixin)`；`_run_stages_from` 核心枢纽保留主类。累计 12281 → 8288 行（-3993），零公共 API 破坏。
- **落地记录（2026-08-18 九轮）**：P0-A3 tenant 表迁移——`tenant_quotas`/`tenant_usage_ledger`/`tenant_policies` 的 DDL + CRUD 从 core ExecutionStore 迁至 platform `TenantStore`（`aiPlat-platform/tenants/tenant_store.py`，同库零数据迁移）。core 侧 `core/services/tenant_store_protocol.py`（协议 + 注册表）经 CoreFacade re-export，platform 挂载时 `set_tenant_store()` 注入；policy_gate/llm/engine 等 9 个 core 消费方 + 6 个 platform router 改注入优先（fallback execution_store）。宪法测试从 DEPRECATED marker 豁免变为真过。
- **落地记录（2026-08-18 十轮）**：P1-A3 子代理 provider 接线收官——`SubagentProvider` 抽象（capabilities 旗标 + start/continuation/interrupt）已有 `InProcessProvider` + `ACPProvider` 两实现；本次：① `execute_parallel` 增加 `provider` 参数（非空走 `execute_with_provider`，默认行为零变化）；② coordinator 新增 `send_message`（DSH send_message 工具等价）+ `get_instance_status`（running/waiting/settled 三态）+ `interrupt_instance`；③ dynamic_orchestrator 生产路径按 `AIPLAT_SUBAGENT_PROVIDER` 选择 provider（默认 in_process 不变）；④ 修复 InProcessProvider.start 假成功 bug（execute_single 返回 SubagentResult 时错误读 summary）；⑤ registry 清理过时 `SubagentProviders` 条目；⑥ 新增 14 项单元测试（`test_subagent_providers.py`）。
- **落地记录（2026-08-18 十一轮）**：P1-A4 消息渠道适配器收官——`get_channel_adapter(name)` 统一解析（7 渠道：3 内置 + 4 扩展 discord/wecom/email/dingtalk，`wecom`→`wechat` 别名）；扩展适配器注册进 `ChannelDispatcher`；platform `test_channel` 端点校验适配器存在（fail-loud 422）；registry 补登；6 项渠道单测。
