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
- **落地记录（2026-08-19 二十九轮）**：GraphRAG `_vector_search` 真向量化——从"伪向量"（wiki FTS 名义）改为**优先 kb_embeddings 真语义检索**（SqliteEmbeddingRetriever，domain/default 双租户尝试），无向量数据时 fallback wiki FTS。契约：GraphRAG 实体路由后的取块为真语义相似度（向量库有数据时），不再依赖 wiki 关键词。
- **落地记录（2026-08-19 三十轮）**：本体学习管理面板——后端 `GET /ontology/suggestions`（pending 建议列表：new_class/new_property/new_subclass/merge_classes）+ 前端 `OntologyLearningPanel`（挂载于本体模型管理页：建议展示 + 刷新 + OWL 导出按钮，调 `GET /ontology/export/learned` 展示 Turtle）。契约：本体学习闭环从 API 延伸到管理 UI。
- **落地记录（2026-08-19 三十一轮）**：P0-L2 业务事件桥（六层框架 GPS 层）——`AsyncActionRegistry.execute` 动作成功后发布 `BUSINESS_ACTION` 事件（observability EventBus 审计）+ `business_event_bridge` 即时增量更新 GraphIndex（`add_entity`+`add_entity_property`，实体状态随业务动作变化，替代"定期 ABox 全量重建"）。契约：业务动作（签署/审批/状态变更）→ 本体实例即时反映，AI 从"问诊式"升级为"哨兵式"。首个接入动作：Action Registry 执行成功。
- **落地记录（2026-08-19 三十三轮）**：P1-L3 本体公理约束编译（六层框架 L3 大脑层）——`ontology_constraint_compiler`（AXIOMS description + 类 required_fields → 自然语言硬规则块）+ `prompt_assembler` opt-in 注入（`meta.inject_ontology_contract` 时编译注入 system prompt，默认不注入保 prompt cache 稳定）。契约：AI 生成前知道业务红线（如"概念必须关联来源"），事前约束从编码契约扩展到本体公理。
- **落地记录（2026-08-19 三十四轮）**：P1-L4a EAEV 反事实扰动（六层框架 L4 交规层）——`hallucination_tracker.counterfactual_perturb`：抽取最高频实体 → 替换为无关 token → 同上下文重验 → 置信度漂移 >0.3 且原置信度 >0.6 判定"记忆惯性幻觉"（模型靠预训练记忆硬撑，非证据支撑）→ claim.quality_flag=needs_review；evaluate 循环内 best-effort 接入。契约：EAEV 从"正向证据验证"升级为"反向压力测试"。
- **落地记录（2026-08-19 三十五轮）**：P1-L4b SIRG 推理链审计（六层框架 L4 交规层）——`sirg_auditor`：`rule_chain_for(conclusion)` 提取本体标准规则链（结论 relation 匹配）+ `audit_reasoning(实际触发规则, 结论)` 对比缺失/多余规则 → 可解释违规报告（"推理跳过了 XXX 条规则"）。实际推理链取自可观测执行面（decision_trace/工具调用审计/inference rule_hits），不依赖 LLM 内部表示。契约：可解释性——不仅记录"做了什么"，还审计"推理是否符合本体规定路径"。
- **落地记录（2026-08-21 三十六轮）**：P2-L1 本体分层治变（治理工程化层）——`OntologyClass.tier`（core=稳定核心/全员架构评审、logic=可变逻辑/产品侧确认、edge=实验边缘/自服务，默认 logic 兼容存量 YAML）+ `ontology_loader` 解析/校验 + `versioned_ontology_store.approve_proposal` 按 tier 分级审批 + `apply_proposal` tier gate（core 变更必须已通过架构评审 `approval_level=core`；edge→logic 升格必须携带 `promotion_proof.reuse_count ≥ 3` 复用证明）+ `ontology_audit` 报告新增 `tier_distribution` 分组。契约：本体变更治理从"一刀切审批"升级为"按影响半径分级"——承重墙变更阻断直至架构评审，沙盘变更自服务但绝不自动升格。测试：`test_ontology_tier.py`（10 例：解析/校验/impact 聚合/升格检测/角色矩阵/审批门/apply gate/审计分组）。
- **落地记录（2026-08-21 三十七轮）**：P2-L0 立项四问工具化（六层框架 L0 战略罗盘层）——`core/apps/fde/service/four_questions.py`：四问（决策反复发生 / 跨 3+ 系统 / 有 Owner+量化指标 / 可写回 Action）逐项打分（0-100）加权 → 总分 + 结论（go ≥75 / conditional 50-74 / sandbox <50）+ MVP 本体建议 tier（edge/logic，复用 P2-L1 分层语义）。FDE 诊断卡端点：`GET /fde/diagnostics/four-questions`（元信息）+ `POST /fde/diagnostics/four-questions/evaluate`（评估）。契约：立项从"拍脑袋"变为"可度量决策性价比"，MVP 本体分层引导显式化。
- **落地记录（2026-08-21 三十八轮）**：P2-L5 Action 阶梯量化门（六层框架 L5 受控行动层）——`ActionContractModel.action_level`（ActionLevel：lv1_readonly→lv4_auto_close，默认 Lv2 保守）+ `AsyncActionRegistry.compute_closure_gate`（Lv4 自动闭环前检查历史误报率：result_status ∈ rejected/corrected/rolled_back/overridden 视为误报，fp_rate < 0.5%（CLOSURE_FP_RATE_MAX）才允许闭环；超标 → 降级人工确认（走 approval gate）或返回 closure_gated）。顺手修复 `_get_entity` 潜伏缺陷（`g.get()`→`g.get_node()` + GraphNode→dict，此前 GraphIndex 实体加载恒失败）。契约：自动闭环必须有"真实业务考验"的误报率背书，杜绝无历史记录的自动作恶。
- **落地记录（2026-08-21 三十九轮）**：数字人管线 P0/P1 修复（digital_human）——① P0-1 registry 双实例：`voice_pipeline` 改用 `core.apps.agents.get_agent_registry`（discovery 模块级单例，server 启动时 `AgentManager._bridge_to_registry` 注册全部 workspace agents 含 materials_chat）；此前用 `integration.get_agent_registry` → DI 解析 `lambda: AgentRegistry()` 传参 TypeError → fallback 新建空实例，`registry.get("materials_chat")` 恒 None，回答退化为 echo"收到: {text}"。修复后单例含 41 agents 且 materials_chat 可解析，另加"模型解析失败降级空 model + 直接创建"兜底链。② P0-2 ASR 转写：`InfraAudioAdapter.transcribe` 返回 `List[Dict]`（segment 列表），此前 `str(result)` 把整个列表序列化为垃圾文本；改为按 segment 顺序拼接文本。③ P1-1 `digital_human` ControlProfile（口语化/中高温/宽松门控）从死 import 变为入口 `set_profile_override` 实际应用。契约：数字人回答从此真正走 MaterialsChatAgent 知识问答链路（system_docs 集合 + CRAG 4 级检索 + 幻觉校验）。测试：`test_voice_pipeline_fixes.py` 6 例（segment 拼接/旧式 dict 兼容/空结果/discovery 单例断言/直接创建兜底/echo 双保险）。
- **落地记录（2026-08-21 四十轮）**：数字人管线剩余问题修复（digital_human P1/P2）——① P1-3 格式链统一：TTS 输出 WAV，WS 响应加 `format: "wav"` 字段，前端按真实格式设置 `data:audio/wav` 播放（不再硬编码 mp3）；前端 MediaRecorder 录音 webm → 后端按字节魔数嗅探（EBML 0x1A45DFA3 / OggS / RIFF）决定临时文件后缀，避免 .wav 扩展名误导解码器。② P1-2 轨迹闭环：`trajectory_collector.export_sharegpt_dataset` 把 `~/.aiplat/trajectories/` 的对话轮次聚合为 ShareGPT JSONL（`{conversations:[{from:human/gpt,value}]}`，与 auto_trigger._convert_to_sharegpt 同构）→ `~/.aiplat/training/sft_digital_human_*.jsonl`，会话结束（finally）best-effort 触发——数字人对话首次进入 SFT 训练闭环（此前 0 消费者孤岛）。③ P2-1 WS 鉴权：`AIPLAT_VOICE_WS_TOKEN` 配置后握手校验 `?token=`（未配置保持开放兼容开发），前端经 `VITE_VOICE_WS_TOKEN` 携带。④ P2-2 生产 WS 路径：优先 `VITE_WS_URL`，其次 dev 5173 替换 8002，缺省同域——修复生产域名连不上问题。⑤ P2-3 小问题：ws.onerror 闭包不再引用过期 status；录音 10s 最大时长上限（原注释声明未实现）；`generate_answer`/handler 支持 `session` 参数隔离多用户对话记忆与轨迹（前端每次会话随机生成 `dh_<ts>_<rand>`）。契约：数字人从"复读机"到"知识问答 + 可治理 + 可训练"完整闭环。测试：`test_voice_pipeline_fixes.py` 10 例。
- **落地记录（2026-08-21 四十一轮）**：数字人页面实时数据感知（P2-4，L2 动态感知延伸）——前端新增 `pageDataBridge.ts`（`reportPageData(route,data)`/`getPageData`/`pageDataToText` 全局数据桥，页面自愿上报结构化状态），FloatingDigitalHuman 发 context 时附带当前页面上报数据；后端 `voice_chat_handler` 解析 context.data → `run_ctx["page_data"]` → `MaterialsChatAgent` 将页面数据摘要拼入 `enhanced_question`（`[当前页面数据: ...]`，限长 800 字符）。示范接入：诊断概览页上报 layerStatus/unhealthyLayers/guardResult/diagRunId。契约：数字人从"只知页面叫什么"升级为"知道当前画面状态"——在诊断页可答"当前系统健康吗"（能引用 infra=healthy/core=degraded 等实时值）。零侵入：未上报页面行为不变。测试：`test_voice_pipeline_fixes.py` 12 例（含 page_data 注入/空值不注入）。
- **落地记录（2026-08-21 四十二轮）**：数字人页面数据感知扩展（P2-4 批量接入）——8 个管理页面接入 `pageDataBridge` 上报实时状态：诊断概览（layerStatus/unhealthyLayers/guardResult）、告警中心（firingCritical/Warning/Info）、治理仪表盘（overallHealth/pendingApprovals/机制状态）、Agent 管理（statusCount/running/error）、模型管理（enabled/disabled/unhealthy）、可观测性（activeRuns/topErrors/llmErrorRate）、运行记录（runStatus/eventKinds）、本体编辑器（domainCount/classCount/selectedClass）。数字人可在各画面回答状态类问题（"有几个告警在触发？"→引用 firingTotal；"治理健康分多少？"→引用 overallHealth）。契约：页面接入成本 = 一个 useEffect + reportPageData(route, data)，卸载时 clearPageData 防陈旧数据；route 与 pageManifest 严格一致。
- **落地记录（2026-08-22 四十三轮）**：文档同步守卫补盲区（doc→code 对账）——根因：同步机制是"按代码变更触发"（contracts-guard/verify_doc_sync 只盯 code→spec 绑定），而专项审计报告（docs/research/*.md）是"按文档陈述触发"，无任何机制对账 → 知识管理审计报告 v2 停在 P0-3 时点、P1-1/P1-2 实际已修复却仍标待修。实施：① Rule 6（verify_doc_sync.sh + 独立脚本 `scripts/check_research_docs_freshness.py`）扫描 research/*.md 的状态标记（已修复/已实施 vs 待修/空壳/🟠🟡🔴）与反引号代码符号引用，验证符号存在、状态不矛盾；WARNING 级，--ci 阻断。② 审计报告自校验字段：报告头部 `> **最后验证：DATE**`，Rule 6 检查引用的代码文件 mtime 是否晚于该日期（+1 天宽限）→ 提示重新验证。③ 知识管理审计报告 v3 补"最后验证"头。契约：专项审计文档从此有自动化新鲜度防线，文档过时不再依赖"人主动问"。测试：`tests/tool_correctness/test_research_docs_freshness.py` 8 例（符号存在/类名/豁免/缺失/矛盾/时间戳/CLI）。
- **落地记录（2026-08-22 四十四轮）**：应用工厂（AI App Factory）功能分析 + 数字人页面感知接入——① 分析确认：`/app/factory`（AIFactory 3 模式容器）与 `/app/builder/projects`（ProjectsPage 纯列表）共用后端 `/platform/builder/projects`；生命周期 10 步（对话澄清→PRD→组队（recommend_team 注入 Agent 历史性能表 first_pass/rejection/qa_rollback）→流水线执行（core PipelineEngine）→HITL→修复→回滚→部署（按测试通过率算 pass_rate）→预览）。② P2-4 扩展：应用工厂页接入 `reportPageData('/app/factory', ...)`（projectCount/stageCount/running/done/avgPassRate/selectedProject/选中项目阶段）——数字人可答"几个项目在跑/平均通过率/当前项目阶段"。③ 操作手册更新（三模式 + 生命周期 + 双入口说明）。契约：数字人第 9 个感知页面；应用工厂从"手工点按钮"到"可对话查询状态"。
- **落地记录（2026-08-22 四十五轮）**：应用工厂双模式真相补全 + pass_rate 标注（P2-4b 揭露深化）——① 双模式自动路由确认：`planning_agent` 分析 PRD 后输出 `mode` 字段（`team_planner.py:471-476`："核心是自然语言交互（agent）还是确定性计算/API（code）？"）→ `builder_project_service.py:1019` 映射固定团队模板（agent→default.yaml 配置生成，code→code.yaml 真实代码生成含 `uses_file_output`/`deploy_files_to_disk`/真 pytest）；② pass_rate 修复：`deploy_to_app` 现显式标注 `pass_rate_source`（real_pytest=真实测试 / estimated=按产物长度估算）+ `pass_rate_estimate_reason`，消除"字数即质量"误导；③ 操作手册补双模式章节。契约：应用工厂不是单一"配置生成器"而是**双模路由器**；pass_rate 数值不再无来源。
- **落地记录（2026-08-22 四十六轮）**：应用工厂全面分析报告（docs/research/应用工厂分析报告.md）——全链路代码实证（前端 3 模式 + 后端 40+ 端点 + core 引擎 + 双模式自动路由 + 落盘/测试/部署）。核心结论：应用工厂是"AI 驱动的双模应用产线"——planning_agent 按需求自动判断 agent（配置生成）/code（真实代码生成），统一引擎执行；三处诚实标注（pass_rate 估算、前端配置式、测试依赖用例质量）。报告每节附 `文件:行号` 证据，Rule 6 验证全绿。
- **落地记录（2026-08-22 四十七轮）**：SystemGraph 页面 404 修复——前端 `SystemGraph/index.tsx` 5 处 code-intel API 用旧前缀 `/api/core/diagnostics/code-intel/*`，实际后端挂载于 `/api/platform/apps/diagnostics/code-intel/*`（platform misc router，routes.py:7286 prefix=/api/platform/apps）→ 全部修正。诊断确认：① knowledge-graph（`/api/core/knowledge-graph/*`）由 core 自动发现正常加载，无需改；② `/api/core/diagnostics/*`（core diagnostics router）正常；③ AIFactory chunk 404 为浏览器缓存旧 index.html 引用旧 chunk 哈希（dist 已重建新哈希），强制刷新即可，非代码 bug。契约：前端 API 路径必须与实际挂载前缀一致（core 自动发现 /api/core、platform apps /api/platform/apps）。
- **落地记录（2026-08-22 四十八轮）**：应用工厂 L2 设计文档（导入既有代码输入通道）+ Rule 6 守卫适配——① `docs/research/plan-app-factory-l2-import-repo.md`：设计"从 0→1 生成器 → 1→100 演进器"第一步——`import-repo` API（zip/路径导入→manifest→_final_state.imported_repo）+ code_generation prompt 注入被引用文件 + 安全（zip-slip/路径白名单/密钥过滤/体积限制）+ 回滚 + 7 项验收，约 2 天工作量。② Rule 6 守卫适配：`plan-` 前缀设计文档的目标态路径/符号不参与"现状代码引用"对账（避免把规划示例当过期引用误报），`is_plan` 跳过引用检查。契约：设计文档描述未来目标态，与现状审计文档（research 非 plan 前缀）分开对待。
- **落地记录（2026-08-22 四十九轮）**：L2 导入既有代码实施（应用工厂演进器第一步）——① `import-repo` API（platform）：zip/路径 → `~/.aiplat/apps/{pid}/imported/`（与部署目录隔离）→ manifest（path/size/sha256/lang/first_line，跳过 .env/*.pem/secrets/.git）→ `proj.imported_repo`；安全：zip-slip 拒绝 + existing_path 白名单（AIPLAT_HOME 内）+ 限额（50MB zip/500 文件/2MB 单文件）+ prev 快照。② prompt 注入（core）：`PipelineStageConfig.inject_imported_context` 配置驱动——`_run_stage_skill` 把 platform 组装的 `behavior_prompt`（重写而非合并契约）+ `intent_anchor_block`（{path,intent} 意图锚点）+ 被引用文件全文（200KB 上限）+ 其余文件清单附加到 stage 输入；引擎零业务文案（§5.8 边界，文案全部由 platform 组装）。③ 测试门禁逃生：`skip_pytest_gate` → `test_execution_mode=pytest` 阶段短路（`APPROVED_SKIPPED` + `_skip_pytest_gate`/`_test_gate_skipped_reason` 标记）→ deploy 走 estimated 带显式 reason；`has_tests`/`missing_deps` 检测随 import-repo 返回。④ 部署警告 + 埋点：deploy_to_app 写 `regenerated_warnings`（Build Log 刷屏 "File xxx has been regenerated, please review diff manually."）；`GET /import-stats` 统计 skip 比率 >40% 触发 L3 优先级告警。契约：L2 是"整文件重写"非"增量合并"（语义透明：前端红字警告 + 手册弹窗），回滚靠 `imported/` 原件 + prev 快照。测试：`test_l2_import_context.py`（core 注入/跳过门禁 4 例）+ `test_l2_import_repo.py`/`test_l2_import_helpers.py`（platform 静态 20 + 动态 10 例）。
- **落地记录（2026-08-23 五十轮）**：L3 增量合并引擎实施（plan-app-factory-l3）——① `merge_engine.py`（platform）：ImpactAnalyzer 影响面分析（勾选 + Python 一阶 import 引用，含叶子模块名 fallback）+ DiffMerger（unified diff 预览 + 语法 py_compile + 接口 AST 验证 + apply 前 deploy.prev 快照 + imported 基线复制）。② prompt 策略：`merge_strategy`（full_rewrite 默认 / incremental_merge）由 platform 选择注入 `_L3_INCREMENT_PROMPT`（只改相关区域/其余逐字节一致/`## UNCHANGED` 标注）或 L2 重写契约——引擎仍零业务文案，仅新增 `_deploy_file_blocks` 剔除 `## UNCHANGED:` 标记（通用输出格式约定）。③ 审批门禁：merge-apply 前逐文件校验（语法/接口失败阻断），前端逐文件 diff 审批（通过/驳回），未提及文件保留 imported 原件。④ 契约：run 事件与 `deploy.prev` 快照保证 merge 可追溯；`regenerated_warnings` 记录 `Merged N files (incremental_merge)`。测试：`test_l3_merge_engine.py`（动态 10）+ `test_l3_merge_static.py`（静态 7）。
- **落地记录（2026-08-23 五十一轮）**：L5 v2（infra 集成 + 金丝雀权重）——① `infra_bridge.deploy_app_service`（core→infra 桥接，standalone-safe no-op）+ `CoreFacade.deploy_app_service` re-export：platform 经 facade 注册服务（namespace=aiplat-apps），修复 L5 v1 platform 直导 infra 违规（单向依赖 platform→core→infra）。② 金丝雀权重路由：发布记录 `canary_weight`（0/10/50/100，canary 设权重默认 10，full 强制 100，rollback 置 0）——权重为路由配置表达（部署环境消费）。③ 契约：发布状态机与权重同存 releases 记录（append-only）；infra 注册仅 `AIPLAT_L5_INFRA_DEPLOY=true` 时经桥接触发。测试：`test_l5_release.py` TestCanaryWeight 4 例 + `test_l5_release_static.py` TestL5V2Facade 5 例。
- **落地记录（2026-08-23 五十二轮）**：安全降级审计事件（安全体系审计报告 §4.1 方案 B）——`policy_gate.py` skill_load 权限规则 except 路径（`resolve_skill_permission` 因 core_facade/DB 不可用被跳过，fail-open）记录 `execution_store.add_audit_log(action="security_degraded", kind="skill_permission_resolver_unavailable", ...)`（含 user_id/tool/skill/error）——降级放行可审计追溯，行为不变（fail-open 保留）。测试：`test_policy_gate_skill_load_permissions.py::test_security_degraded_audit_wired`（静态接线断言）。
- **落地记录（2026-08-23 五十三轮）**：G6 CC/Codex hooks 协议桥（对标报告 §20 唯一完全缺失项闭环）——`cc_bridge.py`：`load_hooks_json`（CC 嵌套/Codex 数组双格式解析 + 非 command handler 跳过）+ `CCHookBridge`（command handler 执行器：shell=False shlex 拆词、`asyncio.to_thread`、超时 30s、stdout/stderr 捕获、结构化结果）+ `register_cc_hooks`/`load_cc_hooks_if_configured`（默认关）；`cc_bridge_rules.py` 数据驱动映射表（CC 7/30 + Codex 4/10 事件→HookPhase）；`HookManager.__init__` 配置存在时装载（`~/.aiplat/hooks.json` / `AIPLAT_CC_HOOKS_PATH`）。契约：外部 hooks 事件经 `SESSION_START`/`PRE_TOOL_USE`/`POST_TOOL_USE`/`STOP` 等生命周期阶段注入 hook 链（run 级事件语义不变，hook 触发属会话层扩展）；command 以 repo cwd 执行、权限继承执行者身份（企业场景需 RBAC/审计配合）。测试：`test_cc_hooks_bridge.py` 15 例。
- **落地记录（2026-08-23 五十四轮）**：渠道广度延伸（7→10，Hermes 22 平台广度对齐方向）——`aiPlat-app/channels/adapters/whatsapp.py`（WhatsApp Cloud API webhook：entry/changes/value/messages/contacts 解析，format_response messaging_product）+ `lark.py`（飞书事件回调：event.message.content JSON 字符串解析，msg_type=text）+ `teams.py`（Teams Bot Framework activity：conversation/from/serviceUrl，type=message）；`ChannelType` 补 WHATSAPP/LARK/TEAMS 枚举 + `ADAPTERS` 注册（3 内置 + 7 扩展 = 10）。契约：渠道适配是 app 层归一化职责（统一 `ChannelMessage`），platform `POST /channels/{id}/test` 经 `get_channel_adapter` 动态解析自动覆盖新渠道（零 platform 改动）；未知渠道 ValueError。测试：`test_cli_and_channels.py` 10 例（含 3 新适配器 parse/format 样例）。
