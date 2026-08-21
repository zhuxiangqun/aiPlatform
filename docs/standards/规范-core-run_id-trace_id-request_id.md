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

> **状态标注（P0-C2 更新，2026-08-19）**：`request_dedup` 表**已实现**（`core/services/execution_store_schema.py` 建表 + runs_mixin 幂等映射）。本节为当前实现描述。

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
- **落地记录（2026-08-18 十二轮）**：P0-A1 harness→apps 服务调用收敛——9 处 lazy 直导改为经 integration.py DI 解析（get_subagent_coordinator ×2 / get_agent_registry / get_mcp_client_manager / get_skill_discovery / get_job_manager / get_dataset_manager ×2 / get_result_verifier，新增 5 个工厂）；宪法白名单 38→25（-13：9 收敛 + 4 stale）；data type / static util / optional lazy 保留白名单（设计合法）。
- **落地记录（2026-08-18 十三轮）**：P0-A2 api→CoreFacade 收敛——54 个 api 文件 292 行 harness 直导改为经 `core.api.core_facade`（执行引擎核心模块 kernel.runtime/integration/model_injection 公共符号/syscalls.llm/approval 直导清零）；CoreFacade 模块级补 `sys_llm_generate` re-export；顺带修复 wiki.py 存量死 self-import；69/69 routers 导入通过。剩余 api→core.harness 直导 299 处为 knowledge 域（wiki/ontology/code_graph 知识检索能力，非执行引擎，CoreFacade 部分已 re-export，渐进跟进）。
- **落地记录（2026-08-18 十四轮）**：P0-A10 Builder E2E 修复——3 处测试基建：① `test_model_category_routing` mock `create_selected_adapter` + `best_model_for_purpose`（本地无 env 模型 + RAM 5.5GB 硬件加载失败）；② `test_checkpoint_persistence_roundtrip` 传 mock model（构造懒加载）；③ `test_recommend_team_no_name_error` 路径改 `__file__` 相对（pytest cwd 漂移）。20/20 passed，守卫 §17 warn 级自动放行。
- **落地记录（2026-08-18 十五轮）**：P0-5 阶段 3 MFA 强制策略——`POST /tenant/api-keys` 对 admin 角色强制 MFA（未启用 → 422 `mfa_required`）；CLAUDE.md §11b 从"建议"升级为"强制"（附 verify 块）；MFA 测试 7→9 项（TOTP 生成/校验/URI/启用判断/角色强制/端点强制/端点放行）。流程：`POST /platform/auth/mfa/setup` → 扫码 → `POST /platform/auth/mfa/verify` → 激活。
- **落地记录（2026-08-19 十六轮）**：行动纲领 3 个部分项闭环——① P0-C3 registry→docs 漂移根治：9 符号补登（190 全同步）+ pre-commit Step 2.7 自动补登；② P0-B4 CoreFacade getter 冗余清零：删除 `get_agent_registry_facade`（统一 `get_agent_registry` canonical re-export + conversations.py 收敛）+ 清理 `_get_trend_alias`；91 个 get_* 符号 0 调用者清零；③ P0-B5 opt-in flags 文档化：新增 `docs/standards/规范-功能开关与配置.md`（49 个默认 false 开关分组登记 + 登记义务）。
- **落地记录（2026-08-19 十七轮）**：P0-A2 收敛回归修复——knowledge-graph/stats 500 根因（CoreFacade 未 re-export `effective_cycles` 等符号导致 ImportError）→ 全仓审计 `from core.api.core_facade import` 缺失符号：**61 个符号 20 文件**恢复原模块导入（保留合法 CoreFacade 收敛）；移除 triple_scanner 引用不存在 API 的死代码（`CoreFacade.get_pipeline_stages` 全仓无定义）；缺失符号清零，stats 端点实测 1738 节点运行成功。
- **落地记录（2026-08-19 十八轮）**：P0-A1 DI 工厂 fallback 系统性验证（P0-A2 教训延伸）——`_resolve_or_import` 13 个 fallback 全检，修复 2 个坏路径：`get_mcp_client_manager`（`core.apps.mcp.client:get_mcp_client_manager` 函数不存在 → 改 `MCPClientManager` 类）与 `get_agent_registry`（`core.apps.agents.registry` 模块不存在 → 改 `core.apps.agents.discovery:AgentRegistry`）。修复前消费方静默降级（profile.list_servers 返回 []），修复后真正工作。
- **落地记录（2026-08-19 十九轮）**
- **落地记录（2026-08-19 二十轮）**：守卫盲区修复——ruff F821 被 pyproject.toml ignore + py_compile 只查语法，导致 PipelineConfig 类 NameError 长期漏检。新增 AST 级守卫 scripts/guard_undefined_names.py（函数内未 import 大写符号，豁免 builtins/嵌套定义/局部 import/赋值），接入 architecture_guard.sh；pipeline_execution 另 2 处 PipelineEngine 直构（115/369 行）改 create_pipeline_engine；新增防回归测试 tests/unit/test_pipeline_execution_undefined_names.py（4 passed）。：应用工厂重新构建无输出修复——pipeline_execution.py `_execute_pipeline` 用 `PipelineConfig` 但从未 import（存量 NameError，P0-A2 前已存在）→ 每次 run 立即 failed 无输出。修复：补 `PipelineConfig` import（3 处）；`rebuild_from_state` 直构 `PipelineEngine`（未 import + 违反宪法 A2）改为 `create_pipeline_engine`（CoreFacade）+ 构造后挂 `_persist_callback`。
- **落地记录（2026-08-19 二十一轮）**：P3-1 双轨一致性校验可见化（对标吸收评估改善项 1）——`get_full_state_from_run_id` 交叉检查升级：快照/事件 phase 不一致时从 debug 静默升级为 **WARNING**（日志含 run_id + snapshot/event phase 详情），`state_event_consistent=False` 保留；读路径保持**无副作用、不阻断**（双写时序合法窗口不误伤）。契约：状态快照与事件折叠派生的一致性从此可观测，run 状态漂移不再静默；新增测试 2 个（漂移告警 caplog 断言 + 无事件跳过校验），engine_state_keys.txt 基线登记 `event_derived`/`state_event_consistent` 两个 P2-A1 通用 key。
- **落地记录（2026-08-19 二十二轮）**：模型选择去除 env 干预（用户决策：LLM 全在 infra 注册表声明）——① 删除死代码 `create_adapter_with_fallback`（0 生产 caller）；② `generate_with_fallback` 去除 `AIPLAT_{purpose}_MODEL` 候选覆盖（候选纯 `select_by_purpose_list` infra 评分）；③ `_build_preferences` 去除 env 偏好（仅 YAML model_overrides）；④ 顺手修复 `pipeline_state.py` 存量缺 `import logging`（checkpoint 持久化 OSError 处理路径 NameError——run 落盘异常时崩溃而非记录日志）。契约：模型选择候选必须来自 infra 注册表，env 不再参与选择（`get_default_model` 的 env 解析保留但已校验，env 未设置返回空无副作用）。
- **落地记录（2026-08-19 二十三轮）**：知识检索修复批次（knowledge 审计）——① `KnowledgeRetriever.search/search_by_type` 增加 `tenant_id` 参数透传（消除直接调用者落默认租户库的风险，检索租户隔离在 API 层收敛）；② `retrieval_quality_gate._score_chunk` 中文 bigram 切词修复（中文相关性评分失真）；③ 图增强 `graph_enhance_query` 复核：execute 绑定数无 bug（原审计误报，实为未使用的 params 死变量已清理），真实问题为 `extract_entities` 0 写入者（kb_graph 空壳，与 kb_embeddings 同类，待接线决策）。
- **落地记录（2026-08-19 二十四轮）**：P0-3 知识双空壳接线——`ExtractionPipeline.run` 增 `tenant_id` 参数，尾部 `_wire_kb` 将抽取关系写入 kb_graph（`_store_triples` 自动建库）与分块写入 kb_embeddings（sqlite_retriever 补 DDL 自动建库）；`graph_enhance_query`/向量检索从恒空变为实测命中。契约：文档摄取后图增强与向量检索可工作（无模型时安全降级）。
- **落地记录（2026-08-19 二十五轮）**：本体学习补全（文档→OWL/TTL 闭环）——`export_suggestions_to_owl`（pending 建议 → 标准 OWL/Turtle，同 export_to_owl_rdf 前缀约定）+ `write_suggestions_owl_file`（落盘 `~/.aiplat/ontologies/{collection_id}.learned.ttl`）+ `_infer_parent_from_label`（subclassOf 层次推导：精确→同义→包含→ConceptPage 兜底）；接线：evolution_runner 生成建议后 best-effort 自动落盘。契约：知识进化时自动产出可审查/可导入的本体文件。
- **落地记录（2026-08-19 二十六轮）**：P1-2 materials_chat 页面感知检索优化——硬编码 wiki title（manuals / management-ui-operation-manual）与全量 `_load_pages`（上限 1000 页）改为 `search_pages(page_label, limit=20, collection_id)` 搜索式加载；本体学习输出端点 `GET /export/learned`（建议→OWL/Turtle 落盘）。契约：页面感知检索不再硬编码业务手册名，大 wiki 检索成本可控。
- **落地记录（2026-08-19 二十七轮）**：本体学习增强——LLM 层次发现维度（Dimension 3：`_detect_hierarchies` 用 embedding 预筛 0.35-0.95 相似对 + `_llm_judge_hierarchy` 轻量 is-a 判断，生成 `new_subclass` 建议，LLM 调用按类前 5 对封顶）；`export_suggestions_to_owl` 支持 `new_subclass`（subject 标签 + rdfs:subClassOf parent 公理，不再标签猜测）。契约：本体学习从"概念发现"升级为"概念 + 层次发现"。
- **落地记录（2026-08-19 二十八轮）**：向量库真语义 embedding 默认化——`AIPLAT_EMBED_BACKEND` 默认从 `hash` 改为 `semantic`（有 InfraEmbeddingAdapter 模型时写真实语义向量，无模型 `_get_semantic_model` 返回 None 安全降级、向量写入跳过；hash 保留为显式离线/测试模式）。实测：默认 semantic 下 `embed_text_semantic` 返回 384 维真实向量。契约：向量库写入从此为真语义（生产有模型时），无模型自动降级不阻断文本入库。
