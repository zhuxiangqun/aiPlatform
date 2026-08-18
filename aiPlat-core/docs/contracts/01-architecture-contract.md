# Architecture Contract（架构契约）

本文件定义 aiPlat 的架构“硬约束”。目标是防止实现随意演进导致：循环依赖、边界失守、治理失效、可观测断裂。

## 1. 分层与边界（MUST）

aiPlat 逻辑上分为：

1) **Kernel / Runtime（内核运行时）**  
负责：上下文传播、syscall 边界、可观测事件、资源/隔离抽象。

2) **Harness（执行框架）**  
负责：Loop（ReAct/Plan&Execute）、Agent/Tool/Skill 调度、context 管理、gates（policy/approval/resilience/trace）。

3) **Apps（业务组件）**  
负责：tools、skills、exec backends、gateway/channels、learning loop 等具体能力。

4) **Server/API（外部接口）**  
负责：HTTP 契约、鉴权、tenant 解析、将请求注入到 Harness。

### 1.1 依赖方向（MUST）

- `core/apps/*` **MUST NOT** 通过包级 `core.harness` 触发 Harness 的重型导入链路。  
  允许导入 **具体子模块**（例如 `core.harness.kernel.runtime`），但必须确保不会引发循环依赖。
- `core/harness/__init__.py` **MUST** 保持轻量（lazy export），不得在 import 时加载 execution/loop/tools 等重型模块。
- `core/server.py` **MAY** 依赖 apps/harness，但 apps/harness **MUST NOT** 反向依赖 server。

> 说明：这条约束用于避免“任意 import 都把系统启动一遍”，并降低循环依赖风险。

### 1.2 Layer Boundary Contract（MUST）

以下边界用于约束 `aiPlat-core` 内部各层职责，防止运行时内核、业务语义、会话编排、执行能力之间的边界失守。

#### Harness Contract

- `core/harness/*` **MUST** 提供统一执行运行时，包括 `run / event / wait / context / queue / registry / syscall` 等共性能力。  
- Harness **MUST NOT** 承载资料问答、视频问答、多资料比较、适用性分析等业务语义决策。  
- Harness **MUST** 解决“任务如何被执行”的问题，**MUST NOT** 解决“业务上本轮该如何回答”的问题。

#### Policy Contract

- Internal Policy / Service **MUST** 提供问题分析、检索路由、回答策略、会话级领域决策等通用能力。  
- Internal Policy / Service **SHOULD** 保持低副作用、可解释、可测试。  
- Internal Policy / Service **MUST NOT** 替代 Skill 承担底层执行细节。  
- `question_analysis / retrieval_policy / answer_strategy` 当前 **MUST** 视为 internal policy modules，而非普通 Skill。

#### Agent Contract

- Agent **MUST** 作为会话/任务编排器，负责上下文整合、策略调用、能力调度、结果写回。  
- Agent **MUST NOT** 直接实现复杂底层检索、索引、切片、存储等执行细节。  
- Agent **SHOULD** 优先通过 Internal Policy 做高层判断，通过 Skill 执行具体能力。

#### Skill Contract

- Skill **MUST** 提供单一职责、明确输入输出、可复用的执行能力。  
- Skill **MUST NOT** 承担系统级高层路由与策略决策。  
- 若某能力本质上属于问题分析、路由规划、回答策略，而非独立执行单元，则 **SHOULD NOT** 优先 Skill 化。

#### API Facade Contract

- `core/api/routers/*` **MUST** 保持薄入口，负责请求校验、身份透传、执行请求封装。  
- API Facade **MUST NOT** 内嵌核心领域策略与业务语义决策。  
- 领域策略、资料问答路由、回答规划 **MUST** 下沉到 Apps/Services/Policy 层。

## 2. 契约优先（MUST）

当出现以下冲突时，处理顺序必须是：
1) 更新实现以符合契约；或
2) 变更契约（需要明确理由 + 风险），并补齐验收用例。

## 3. 扩展点与插件化（SHOULD）

新增能力应优先以“注册/声明”的方式接入，而不是在核心路径硬编码：
- ToolRegistry：工具注册/查询/动态发现
- Skill registry / Skill packs：技能包发布与安装
- ExecDriver registry：执行后端扩展（local/docker/ssh…）
- Gateway adapters/connectors：渠道适配与交付

## 4. 错误与返回结构（MUST）

对外 API 与 syscall 边界处的错误 **MUST** 使用“结构化错误封装”，至少包含：
- `ok`（成功布尔）
- `error.code`（稳定错误码）
- `error.message`（可读信息，避免泄漏敏感内容）
- `trace_id/run_id`（若可用）

## 5. 变更控制与 ADR（SHOULD）

对下列变更 **SHOULD** 写 ADR 或至少在 PR 描述中给出“决策记录”：
- syscall/gate 行为变化
- prompt 组装逻辑变化（stable/ephemeral、cache key、compaction）
- tool/skill 权限模型变化
- exec backend 引入/删除
- gateway/多入口链路变化

推荐将 ADR 放在：
- `docs/architecture/` 或 `docs/design/` 对应子目录

---

## 附录 A：2026-08 P0-P1 架构变更记录

本附录记录 P0-P1 大规模改造期间对 core 边界的变更（满足 PR binding check 的契约更新要求）：

- **宪法合规（P0-A1~A10）**：harness→apps 反向依赖收白名单（`integration.py`）；api→engine 直导收敛 CoreFacade；platform LLM 推理收敛门面；`doc_compressor.llm_summarize` 作为 LLM 摘要唯一通道（§57 上下文组装合规）。
- **facade 收敛（P0-B4）**：删除 30 个 0 调用者 CoreFacade getter（类直用路径保留，§10 入口唯一性）。
- **学习闭环（P1-A1/A2）**：`learn_nudge_hook`（POST_OBSERVE 实时学习触发）+ `learning/skill_curator`（委托 harness/knowledge 实现，不违反 harness→apps 边界）。
- **子代理 provider（P1-A3）**：`SubagentProvider` 抽象 + in_process/acp 双 provider（对齐 DSH 契约）。
- **syscall 边界**：CrossValidationGate 经 CoreFacade + diagnostics 端点接线（条件激活 stub 获得生产调用者）。

**契约不变项**：单向依赖链（app→platform→core→infra）、syscall 三通道唯一性（sys_llm_generate/sys_tool_call/sys_skill_call）、Prompt Cache 稳定性约束均未改变。

## 附录 B：2026-08 P2 架构变更记录（Phase 5）

- **goal judge（P2-A6）**：`event_loop._judge_goal_condition` 每轮评估 goal 触发达成度（内置条件 + judge_expr），未达成在 `iterations_left` 预算内续跑（每次续跑独立 run）；LLM judge 预留未启用。
- **no-agent script 模式（P2-A7）**：cron 触发 `params.mode="script"` 直接执行 bash/sh/python3（零 LLM），fail-closed 入口白名单；无 run 记录，经 scheduler 日志观测。
- **CodeGraph gitignore 感知（P2-B5）**：`should_skip` 增加 `git check-ignore`，未跟踪但被忽略的文件不入图。

**契约不变项**：syscall 三通道唯一性、单向依赖链、Prompt Cache 稳定性约束均未改变；script 模式不产生 syscall 事件（无 LLM 通道）。

- **事件源双写（P2-A1）**：`PipelineRunStore` 新增 `pipeline_run_events` append-only 事件日志（阶段/phase/hitl 事件），引擎状态回调双写；run 状态快照保留（向后兼容），事件供回放/审计/UI 时间线。

- **事件折叠派生（P2-A1 二阶段）**：`PipelineRunStore.replay_run_events` 从事件日志折叠 run 状态（审计交叉验证），`pipeline_state` API 附加 `event_derived` 字段；状态快照保留为快速路径。

- **事件源交叉验证（P2-A1 三阶段）**：`get_full_state_from_run_id` 附加 `event_derived` + `state_event_consistent`（状态快照与事件折叠一致性检查），状态快照保留为快速路径。

- **缓存治理（2026-08-18）**：harness 有界化 4 处无界缓存——`syscalls/file.py:_read_cache`（`_MAX_CACHE=512` 淘汰）、`knowledge/path_planner.py:_discovered_cache`（`_MAX_CACHE`+TTL 清扫）、`apps/a2a/server.py:_tasks`（`_MAX_TASKS` FIFO 淘汰）、`api/routers/observation.py:_diag_buffers`（`_DIAG_TTL`+`_MAX_DIAG_RUNS`）。内存缓存均为临时加速，权威真相是 `run_events`/DB。守卫 §83 同步升级：仅告警无界缓存（§83c）、AST 作用域分析（§83b 只统计持久容器）、大小写不敏感（§83a）。
- **运行时扩展缝（P2-A2 落地）**：`CoreFacade.register_handler` 增加来源门禁——handler 定义模块属危险集（os/sys/subprocess/shutil/builtins）注册即拒绝，未评估模块仅 warn；dispatch 永不触发任意代码执行。白名单方向保持 platform→core 单向依赖。
- **缓存治理二轮（2026-08-18）**：6 处 BOUNDED 缓存补上限——`apps/plugins/manager.py:_slot_archives`（`_MAX_ARCHIVES=128`）、`harness/knowledge/sql_ontology.py:_translators`（DomainRouter 白名单 + `_MAX_DOMAINS=64`）、`services/context_service.py` 过期索引读路径清扫、`harness/utils/model_injection.py:_FAILURE_TRACKER`（`_MAX_FAILURE_MODELS=128`）+ `_model_overrides`（`_MAX_OVERRIDES=256`）、`credential_pool.py:_pools`（`_MAX_POOLS=64`）。§83a 18→8。
- **缓存治理三轮（2026-08-18）**：§83a 归零——`harness/routing/skill_routing.py:_skill_weights`（`_MAX_SKILL_WEIGHTS=512`）、`apps/skills/evolution/engine.py:_latest_predictions`（`_MAX_PREDICTIONS=256`）、`harness/infrastructure/base_model_adapter.py:_model_cache`（`_MAX_MODEL_CACHE=16`）补上限；守卫豁免机制从文件级改为变量名级（仅 `_REGISTRY/_DEFAULTS/_MAP` 等命名本身豁免，运行时 dict 不再误豁免）。§83a 18→0，append 0，LRU 0。
- **MetaAgent 数据驱动实现（P0-C7, 2026-08-18）**：`harness/meta/meta_agent.py` 新增 `get_meta_agent()`——EvolutionEngine meta_analysis step 引用不存在的符号（每次 error，静默失效）已修复；数据驱动聚合失败/健康信号，不引入 LLM。`rule_golden_sample.py --verify` 接入 architecture-guard.yml CI（守卫规则黄金样本验证）。
- **provider YAML 驱动补完（P2-A3）**：`ModelManager._API_PROVIDERS` 硬编码集合改为 `_api_provider_ids()`（从 `config/providers.yaml` 按 `type=external` 派生，5min 缓存，YAML 缺失回退硬编码）；新增 external provider 零代码。

**契约不变项**：syscall 三通道唯一性、单向依赖链、Prompt Cache 稳定性约束均未改变；内存缓存有界化不改任何对外接口签名。
- **PipelineEngine 拆分 Phase 1（P2-A4, 2026-08-18）**：自愈策略 13 方法迁移至 `pipeline_healing.py`（`PipelineHealingMixin`，主类 `PipelineEngine(PipelineHealingMixin)` 继承）。纯结构迁移零语义变化；`_meta_optimize`/`_strategy_*` 等符号定位路径从 pipeline_engine.py → pipeline_healing.py（registry/l4-claims/pyramid/whitepaper_refs 已同步）。
- **PipelineEngine 拆分 Phase 2（P2-A4, 2026-08-18）**：状态持久化 6 方法迁移至 `pipeline_state.py`（`PipelineStateMixin`）。主类继承链更新为 `PipelineEngine(PipelineStateMixin, PipelineHealingMixin)`；`_snapshot`/`_summarize_artifact` 等符号定位路径 pipeline_engine.py → pipeline_state.py。
- **PipelineEngine 拆分 Phase 3（P2-A4, 2026-08-18）**：prompt/eval 域 14 方法迁移至 `pipeline_prompt.py` + `pipeline_eval.py`（2 Mixin）。主类继承链 4 Mixin；`_build_prompt`/`_retry_loop`/`_tri_evaluate` 等符号定位路径更新。
- **PipelineEngine 拆分 Phase 4 收官（P2-A4, 2026-08-18）**：stage dispatch/exec 8 方法迁移至 `pipeline_stage.py`（`PipelineStageMixin`，含 `_dispatch_execute`/`_exec_stage`/`_evaluate_stage_health` 等）。主类继承链 5 Mixin；`_run_stages_from` 核心调度枢纽保留主类。拆分累计 12281 → 8288 行（-3993），零公共 API 破坏，P2-A4 全部 4 Phase 完成。
- **Tenant 表迁移（P0-A3, 2026-08-18）**：`tenant_quotas`/`tenant_usage_ledger`/`tenant_policies` 的 DDL + CRUD 从 core ExecutionStore 迁至 platform `TenantStore`（`aiPlat-platform/tenants/tenant_store.py`，与 ExecutionStore 同 DB 文件 → 零数据迁移）。core 新增 `core/services/tenant_store_protocol.py`（TenantStoreProtocol 接口 + 注册表），经 CoreFacade re-export；platform 挂载时 `set_tenant_store()` 注入。core 9 个消费方（policy_gate/llm/policy engine/runs/plugins/diagnostics/integration×3/exporter）+ platform 6 个 router（quota/policy/tenant_policies/onboarding/learning/ops_exports）改注入优先（fallback execution_store，零破坏）。audit_logs/connector_delivery/tenants 主表留 core（执行基础设施，不在 P0-A3 范围）。

- **子代理 provider 接线（P1-A3, 2026-08-18）**：`SubagentProvider` 抽象 + `InProcessProvider`/`ACPProvider` 两实现（capabilities 旗标 + start/continuation/interrupt，DSH 对齐）。`execute_parallel` 增加 `provider` 参数走 `execute_with_provider`；coordinator 新增 `send_message`/`get_instance_status`（三态）/`interrupt_instance`；dynamic_orchestrator 生产路径按 `AIPLAT_SUBAGENT_PROVIDER` 选择（默认 in_process 零变化）。fail-loud 无假成功；registry 清理过时符号；14 项单测。

- **消息渠道适配器（P1-A4, 2026-08-18）**：`get_channel_adapter(name)` 统一解析（7 渠道：3 内置 telegram/slack/webchat + 4 扩展 discord/wecom/email/dingtalk，`wecom`→`wechat` 别名）。扩展适配器在 `aiPlat-app/channels/adapters/` 注册进 `ChannelDispatcher`（merged）。platform `POST /platform/channels/{id}/test` 校验适配器存在（fail-loud 422）。registry 补登 `get_channel_adapter`。

- **harness→apps 收敛（P0-A1, 2026-08-18）**：9 处 harness lazy 直导 apps 服务改为经 integration.py DI 工厂（`get_subagent_coordinator`/`get_agent_registry`/`get_mcp_client_manager`/`get_skill_discovery`/`get_job_manager`/`get_dataset_manager`/`get_result_verifier`，新增 5 工厂）。宪法白名单 38→25；data type / static util / optional lazy（skill_execution_record/browser_test_engine/video_parser/quality.types/finetune.schemas）保留白名单（非服务调用）。
