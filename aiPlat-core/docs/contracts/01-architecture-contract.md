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

- **消息渠道适配器（P1-A4, 2026-08-18）**：`get_channel_adapter(name)` 统一解析（7 渠道：3 内置 telegram/slack/webchat + 4 扩展 discord/wecom/email/dingtalk，`wecom`→`wechat` 别名）。扩展适配器在 `aiPlat-app/channels/adapters/` 注册进 `ChannelDispatcher`（merged）。platform `POST /platform/channels/{id}/test` 校验适配器存在（fail-loud 422）。registry 补登 `get_channel_adapter`。**2026-08-23 渠道广度延伸（7→10）**：+whatsapp/lark/teams 适配器（WhatsApp Cloud API / 飞书机器人 / Teams Bot Framework），`ADAPTERS` 注册 + `ChannelType` 补枚举；`get_channel_adapter`/`POST /channels/{id}/test` 动态解析自动覆盖，零 platform 改动（对齐 Hermes 22 平台广度方向）。

- **harness→apps 收敛（P0-A1, 2026-08-18）**：9 处 harness lazy 直导 apps 服务改为经 integration.py DI 工厂（`get_subagent_coordinator`/`get_agent_registry`/`get_mcp_client_manager`/`get_skill_discovery`/`get_job_manager`/`get_dataset_manager`/`get_result_verifier`，新增 5 工厂）。宪法白名单 38→25；data type / static util / optional lazy（skill_execution_record/browser_test_engine/video_parser/quality.types/finetune.schemas）保留白名单（非服务调用）。

- **api→CoreFacade 收敛（P0-A2, 2026-08-18）**：54 个 api 文件 292 行 harness 直导改经 CoreFacade（执行引擎核心模块直导清零）；CoreFacade 模块级补 `sys_llm_generate` re-export；修复 wiki.py 死 self-import；69/69 routers 导入通过。knowledge 域（wiki/ontology/code_graph）直导为知识检索能力，渐进跟进。

- **P0-A2 收敛回归修复（2026-08-19）**：knowledge-graph/stats 500 根因（CoreFacade 未 re-export `effective_cycles`）→ 全仓 AST 审计 `from core.api.core_facade import` 缺失符号：core 侧 40 符号恢复原模块导入（core 内部 api→harness 允许）、platform 侧 9 符号 CoreFacade canonical re-export（§92 platform 必须经 CoreFacade）；triple_scanner 移除引用不存在 API 的死代码（`CoreFacade.get_pipeline_stages` 全仓无定义）。约束：新增 platform 经 CoreFacade 访问的符号必须先确认 re-export 存在。

- **P0-A1 DI 工厂 fallback 修复（2026-08-19）**：系统性验证 integration.py 全部 `_resolve_or_import` fallback（13 个）——修复 2 个坏路径：`get_mcp_client_manager`（指向不存在的函数 → 改 `MCPClientManager` 类，修复前 profile.list_servers 静默降级）与 `get_agent_registry`（指向不存在的模块 `agents.registry` → 改 `agents.discovery:AgentRegistry`）。约束：新增 DI 工厂时 fallback 的 `module:attr` 必须真实存在（P0-A2/P0-A1 两次教训）。

- **守卫盲区修复（2026-08-19）**：ruff F821 被 pyproject.toml ignore（eval/exec 误报）+ py_compile 只查语法 → PipelineConfig 未 import（NameError）长期漏检（应用工厂 rebuild 无输出）。新增 AST 级守卫 scripts/guard_undefined_names.py（函数内未 import 大写符号检查），接入 architecture_guard.sh；pipeline_execution 全部 PipelineEngine 直构改 create_pipeline_engine（宪法 A2 合规）；防回归测试 tests/unit/test_pipeline_execution_undefined_names.py。

- **子代理第 3 种传输 ProcessProvider（P3-2, 2026-08-19）**：`SubagentProvider` 家族从 2 扩至 3——新增 `ProcessProvider`（fork 式子进程隔离，DSH fork provider 借鉴）：`start()` spawn `python -m core.apps.agents.subagent.process_runner`（新文件，stdin JSON {name, task, context} → stdout ProviderResult JSON，fail-loud 恒输出 JSON），超时 kill（`AIPLAT_SUBAGENT_PROCESS_TIMEOUT` 默认 120s）+ `PYTHONPATH` 注入 core 根（cwd 无关）+ 环境继承（AIPLAT_HOME 透传）。`_PROVIDER_FACTORIES` 注册 `process`（in_process/acp/process 三态），`AIPLAT_SUBAGENT_PROVIDER=process` 可选。capabilities：external+isolation（真进程隔离）、continuation=False。接线链：factory → coordinator.list_providers/get_provider（生产路径）→ subprocess runner。11 项测试（能力旗标/假 runner 协议往返/坏 JSON fail-loud/模块失败 + wiring 接线链）。子代理传输 2→3 种，缩小与 DSH 6 种传输的广度差距。

- **模型选择去除 env 干预（2026-08-19）**：用户决策"LLM 全部在 infra 注册表声明、不使用 env 干预选择"。① 删除死代码 `create_adapter_with_fallback`（0 生产 caller，被 `generate_with_fallback` 取代）；② `generate_with_fallback` 去除 `AIPLAT_{purpose}_MODEL` 候选覆盖——候选纯 `ModelManager.select_by_purpose_list`（infra 评分），无候选才走 `best_model_for_purpose`（unified_pipeline）；③ `_build_preferences` 去除 env 偏好（仅 YAML `model_overrides`）；④ 顺手修复 `pipeline_state.py` 存量缺 `import logging`。契约：模型选择候选必须来自 infra 注册表；`get_default_model` 的 env 解析保留（P1-4 已加存在性校验，env 未设置返回空、无副作用）；`create_selected_adapter` 的 `AIPLAT_LLM_MODEL` 兼容兜底保留（显式传 model_name 不受影响）。

- **知识检索修复批次（2026-08-19）**：① `KnowledgeRetriever.search/search_by_type` 增加 `tenant_id` 参数透传（检索租户隔离在 API 层收敛，直接调用者不再落默认租户库）；② `retrieval_quality_gate._score_chunk` 中文 bigram 切词（原整段中文 1 token 致相关性 0 分）；③ `graph_enhance_query` 复核：execute 绑定数无 bug（原误报），清理未使用的 params 死变量；`kb_graph` 写入入口 `extract_entities` 0 调用者（空壳，与 `kb_embeddings` 同类——两个"声明未接线"的检索能力，待接线/移除决策）。
- **P0-3 双空壳接线（2026-08-19）**：kb_graph 与 kb_embeddings 从"声明未接线"变为可用——`_store_triples` 自动建库建表；sqlite_retriever 补 `_KB_SCHEMA` + `_connect` 自动建库；`ExtractionPipeline.run` 增 `tenant_id` 参数并接线 `_wire_kb`（关系→kb_graph + 分块→kb_embeddings）。语义边界：kb_graph=文档级三元组图（LLM 抽取，doc_id 关联，graph_enhance_query 文档扩展）、GraphIndex=本体实例图（ABox 构建，GraphRAG 实体路由）——不同语义可共存。
- **本体学习补全（2026-08-19）**：suggestions → OWL/Turtle 输出（export_suggestions_to_owl / write_suggestions_owl_file / _infer_parent_from_label），接线至 evolution_runner（建议生成后自动落盘 `{collection_id}.learned.ttl`，可经 ontology_importer 导入或 Protégé 加载）。层次推导：精确标签→同义词→包含→ConceptPage 兜底。
- **P1-2 + 学习端点（2026-08-19）**：materials_chat 页面感知检索改 `search_pages` 搜索式（去硬编码 title + 全量加载）；新增 `GET /export/learned`（export_suggestions_to_owl + write_suggestions_owl_file 的 HTTP 入口）。
- **本体学习增强（2026-08-19）**：LLM 层次发现（Dimension 3：embedding 预筛 + `_llm_judge_hierarchy` is-a 判断 → `new_subclass` 建议）+ `export_suggestions_to_owl` 输出 `rdfs:subClassOf` 公理（subject 标签直接使用）。
- **真语义 embedding 默认化（2026-08-19）**：embed 后端默认 semantic（InfraEmbeddingAdapter 真实向量；无模型安全降级 None，hash 仅显式离线/测试）。
- **GraphRAG 取块真向量化（2026-08-19）**：`_vector_search` 优先 kb_embeddings（SqliteEmbeddingRetriever 真语义，domain/default 双租户），wiki FTS 降级为 fallback。
- **本体学习管理面板（2026-08-19）**：`GET /ontology/suggestions`（建议列表）+ 前端 `OntologyLearningPanel`（建议展示/刷新/OWL 导出）。
- **P0-L2 业务事件桥（2026-08-19）**：Action 执行成功 → `BUSINESS_ACTION` 事件（EventBus 审计）+ `business_event_bridge` 即时增量更新 GraphIndex（替代定期 ABox 重建）。
- **P1-L3 本体约束编译（2026-08-19）**：`compile_ontology_constraints`（AXIOMS+类字段 → 硬规则）+ `prompt_assembler` opt-in 注入（inject_ontology_contract）。
- **P1-L4a 反事实扰动（2026-08-19）**：`hallucination_tracker.counterfactual_perturb`——实体替换重验 + 漂移判定记忆惯性幻觉。
- **P1-L4b SIRG（2026-08-19）**：`sirg_auditor`——规则链提取 + 推理链 vs 规则链一致性审计（缺失规则 → 违规报告）。

- **P2-L1 本体分层治变（2026-08-21）**：`OntologyClass.tier`（core/logic/edge，默认 logic）+ loader 解析/校验 + `versioned_ontology_store` 分级审批（`approve_proposal`：core 需架构评审角色、logic 产品侧、edge 自服务）+ `apply_proposal` tier gate（core 需架构评审证据；edge→logic 需 `promotion_proof.reuse_count ≥ 3`）+ `ontology_audit.tier_distribution` 分组。契约：本体变更治理按影响半径分级；新增 `POST /ontology/proposals/{id}/approve` 审批端点（platform apps/fde 经 CoreFacade 访问）。10 项测试。

- **P2-L0 立项四问（2026-08-21）**：`core/apps/fde/service/four_questions.py`（evaluate_four_questions：四问加权评分 → 总分 + go/conditional/sandbox + MVP tier 建议）；platform FDE 端点 `GET/POST /fde/diagnostics/four-questions` 经 core.apps.fde.service 访问（与 rapid_insight 同模式）。6 项测试。
- **P2-L5 Action 阶梯量化门（2026-08-21）**：`ActionContractModel.action_level`（ActionLevel lv1-4，默认 lv2_confirmed）+ `compute_closure_gate`（Lv4 误报率门 <0.5% 才闭环，超标降级人工确认）+ `_get_entity` 修复（get_node + dict 化）。7 项测试。

- **数字人管线 P0/P1 修复（2026-08-21）**：`voice_pipeline.py` —— registry 解析改 discovery 单例（`core.apps.agents.get_agent_registry`）+ 直接创建兜底（模型解析失败降级空 model 名）；transcribe 改 segment 顺序拼接（List[Dict] → text）；入口应用 `digital_human` ControlProfile。6 项测试。

- **数字人 P1/P2 修复（2026-08-21）**：① TTS 格式链（format 字段 + wav MIME + webm 魔数嗅探）；② 轨迹闭环（export_sharegpt_dataset → ~/.aiplat/training，会话结束触发）；③ WS 鉴权（AIPLAT_VOICE_WS_TOKEN，query token 校验）；④ 生产 WS 路径（VITE_WS_URL 优先）；⑤ session 隔离 + onerror 闭包 + 录音 10s 上限。10 项测试。

- **数字人页面实时数据感知（P2-4, 2026-08-21）**：前端 `lib/pageDataBridge.ts` 数据桥（reportPageData/getPageData/pageDataToText）+ FloatingDigitalHuman context 附数据；后端 handler→generate_answer→MaterialsChat 注入 `[当前页面数据: ...]` 到 enhanced_question；诊断概览页示范接入。12 项测试。

- **数字人页面数据感知批量接入（P2-4 扩展, 2026-08-21）**：8 个管理页面接入 pageDataBridge（诊断概览/告警/治理/Agent/模型/可观测性/运行记录/本体编辑器），每页一个 useEffect + reportPageData。

- **文档同步守卫 Rule 6（2026-08-22）**：`verify_doc_sync.sh` 新增 research 文档新鲜度对账（独立脚本 check_research_docs_freshness.py）：① 状态标记矛盾检测（已修复 vs 待修/空壳）；② 代码符号引用验证；③ `最后验证：DATE` 时间戳 vs 代码 mtime。审计报告新增自校验字段约定。8 项工具自测。

- **应用工厂页面感知 + 双入口梳理（2026-08-22）**：FactoryPage 接入 pageDataBridge（/app/factory）；确认 /app/factory 与 /app/builder/projects 共用 projectApi 后端，factory 为完整入口。

- **应用工厂双模式 + pass_rate 标注（2026-08-22）**：team_planner mode 自动判断（agent/code）→ 团队模板映射；deploy_to_app 的 pass_rate 加 pass_rate_source（real_pytest/estimated）+ 估算原因字段。

- **应用工厂全面分析报告（2026-08-22）**：docs/research/应用工厂分析报告.md —— 双模式自动路由/生命周期 9 环节/权限模型/5 项诚实标注/评分表。

- **SystemGraph code-intel 路径修复（2026-08-22）**：前端 5 处 /api/core/diagnostics/code-intel/* → /api/platform/apps/diagnostics/code-intel/*（匹配 platform misc 挂载）。core diagnostics / knowledge-graph 路径不变。

- **L2 设计：导入既有代码（2026-08-22）**：plan-app-factory-l2-import-repo.md —— import-repo 输入通道（zip/路径→manifest→prompt 注入被引用文件），安全/回滚/验收完整，约 2 天。
- **Rule 6 plan 文档豁免（2026-08-22）**：check_research_docs_freshness.py 对 plan- 前缀设计文档跳过引用对账（目标态路径非现状）。
- **L2 实施：导入既有代码（2026-08-22）**：import-repo 通道落地 —— platform 组装业务文案（`behavior_prompt` 重写契约 + `intent_anchor_block` 意图锚点），core 引擎仅做通用注入（`PipelineStageConfig.inject_imported_context` 配置驱动，读被引用文件全文 + 清单附加到 stage 输入，零业务文案，符合 §Harness Contract）；`skip_pytest_gate` 逃生（`test_execution_mode=pytest` 短路 → APPROVED_SKIPPED）；deploy `regenerated_warnings` 刷屏 + skip 比率埋点（>40% → L3 告警）。契约要点：L2 = 整文件重写非增量合并，回滚靠 imported/ 原件 + prev 快照；引擎不持有任何 L2 业务字符串（全部由 platform 组装传入 state.imported_repo）。
- **L3 实施：增量合并引擎（2026-08-23）**：merge_engine.py（platform）——ImpactAnalyzer 影响面分析 + DiffMerger（diff 预览/语法/接口验证/apply 快照）；`merge_strategy`（full_rewrite 默认 / incremental_merge）由 platform 选择注入增量行为契约（`_L3_INCREMENT_PROMPT`：只改相关区域/逐字节一致/`## UNCHANGED`），引擎仅新增通用 `## UNCHANGED:` 标记剔除（`_deploy_file_blocks`），仍零业务文案（§Harness Contract）；审批门禁：merge-apply 逐文件语法/接口校验 + 前端人工 diff 审批，未提及文件保留 imported 原件。
- **L5 v2 实施：infra 桥接 + 金丝雀权重（2026-08-23）**：`infra_bridge.deploy_app_service`（core→infra 唯一桥接点，standalone-safe no-op）+ `CoreFacade.deploy_app_service` re-export——platform 经 facade 注册服务（namespace=aiplat-apps），修复 L5 v1 platform 直导 infra 违规（单向依赖 platform→core→infra）；发布 `canary_weight`（0/10/50/100）为路由配置表达，full 强制 100。桥接文件是 core 内 infra 访问的唯一入口（§5.31 infra 单一真相源扩展）。

- **安全降级审计事件（方案 B, 2026-08-23）**：`policy_gate` skill 权限解析器不可用（DB 初始化失败等）时保留 fail-open 决策（deny/ask 规则跳过，后续检查链继续），但新增 `security_degraded` 审计事件（`execution_store.add_audit_log`，action=security_degraded / kind=skill_permission_resolver_unavailable / status=warn，附 tenant/actor/tool/skill/error 上下文）使降级可追溯；审计为 best-effort（store 不可用静默跳过，`# noqa: cleanup-best-effort`）。契约：fail-open 行为不变（安全决策观察点），降级必留审计痕迹；方案 A（fail-closed）保留为安全负责人后续选项。

- **G6 CC/Codex hooks 协议桥（2026-08-23）**：`cc_bridge.py`（hooks.json 解析 + `CCHookBridge` command handler 执行器 + `register_cc_hooks`/`load_cc_hooks_if_configured`）+ `cc_bridge_rules.py`（CC 7/30 + Codex 4/10 事件→HookPhase 数据驱动映射表）；`HookManager.__init__` 配置存在时装载（`~/.aiplat/hooks.json` 或 `AIPLAT_CC_HOOKS_PATH`，默认关）。契约：仅 command handler（http/mcp_tool/prompt/agent 跳过记 WARNING）；unmapped 事件 fail-open 不静默执行；command 以 repo cwd 执行、权限继承执行者身份（企业场景需 RBAC/审计配合）；v1 无分层发现/热重载（进程级单配置）。

- **P0-a stdio JSON-RPC 持久内核（2026-08-24）**：`core/acp/stdio_server.py`（`StdioKernel` + `handle_request` + `_event_loop`）——把 aiPlat 内核能力暴露为 JSON-RPC over stdio（JSONL）协议：`thread/start|status|events|resume|approve|reject|rollback|cancel` 映射到已有 `create_pipeline_session`（start/approve/reject/rollback/resume）+ `PipelineRunStore.list_run_events` + `cancel_pipeline`；`item.event` 流式推送 run_events；JSON-RPC 2.0 错误信封 + 背压 `-32001`（对齐 codex app-server）。契约：stdio 协议是**薄映射层**（不新增业务逻辑，全部委托已有门面）；`CoreFacade.start_stdio_kernel` 为唯一入口（server 启动 `AIPLAT_STDIO_KERNEL=1` env 门控）；独立进程 `python -m core.acp.stdio_server`；单进程会话池（进程内 thread_id → PipelineSession），v1 无跨进程会话持久化（断线恢复 = 同进程内 thread/resume）。

- **P0-b 竞品会话/记忆导入（2026-08-24）**：`core/harness/memory/import_claude_sessions.py`（`parse_claude_session`：Claude JSONL user/assistant 配对 + system-reminder 跳过 + text/block-list content 提取；`find_claude_sessions`：~/.claude/projects|transcripts 递归；`import_claude_sessions`：→ MemoryManager.save_interaction）+ `CoreFacade.import_claude_memories` + platform `POST /platform/memory/import`（require_auth）。契约：导入记忆必须带**防投毒溯源**（source_tag=claude_import + provenance=`claude:{session_id}`，对齐记忆系统 §5.12 投毒防御三字段）；单会话失败不阻断整体（best-effort + errors 列表）；记忆写入走 MemoryManager 统一通道（不直写 SQLite）；导入源是只读消费（不改 Claude 源文件，对齐 Codex"源端不动一字节"）。

- **P1 SDK stdio 内核客户端（2026-08-24）**：`aiplat-sdk/aiplat/stdio.py`（`StdioKernelClient`：spawn `python -m core.acp.stdio_server` + JSON-RPC over stdio，thread/start|status|events|resume|approve|reject|rollback|cancel + `stream_events` 轮询式流式监听 + 错误信封/超时；可注入 transport 便于测试）+ `aiplat.__init__` 导出。契约：SDK 是**纯客户端**（不包含业务逻辑，只封装协议）；经 `AIPLAT_STDIO_PYTHON`/kernel_cmd 可指向任意 Python 环境（默认当前解释器）；对齐 Codex SDK 的"程序化启停 Thread + 流式监听事件"（G17 闭环）。

- **P1 OS 原生沙箱执行器（2026-08-24）**：`core/harness/infrastructure/os_sandbox.py`（`detect_sandbox_mode`：bwrap/seatbelt/无探测 + `AIPLAT_SANDBOX` 开关；`build_os_sandbox_cmd`：bwrap 参数构造 `--ro-bind` 系统路径（/usr /lib /bin /etc/ssl 等）+ `--bind` 工作区/tmp + `--unshare-net`（默认隔离网络）+ `--die-with-parent`；seatbelt `sandbox-exec -p` deny-default profile；`sandbox_env_ready` 诊断）。接线：`StageSandbox.run` 包装 worker 子进程（`AIPLAT_SANDBOX=bwrap/seatbelt` 时）+ `CoreFacade.get_os_sandbox_status`。契约：OS 沙箱是**可选加固层**（现有 setrlimit 进程级沙箱保持默认）；无 bwrap/seatbelt 二进制或包装失败时 **fail-open 回退原命令**（与安全降级方案 B 的"决策不受基础设施故障影响"哲学一致）；bwrap 参数白名单固定（系统路径只读、工作区可写、网络默认隔离）。
