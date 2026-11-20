---
doc_type: Reference
status: active
authority: supporting
doc_id: CAPABILITY_IMPACT_MATRIX
---

# Capability Impact Matrix

> Auto-generated from `capability_registry.yaml`
> Version: 1.1.0 | 34 domains | 3037 capabilities (caps_count) | 3037 symbols (provides)

> 口径：`caps_count` 应对齐 `len(provides)`（登记公开符号数）；勿与 `AIPLAT_CAPABILITIES.md` 产品能力行计数混算。

## Consumer-to-Capability Dependencies

### aiPlat-infra/infra/management/model/config_loader.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 6 | adapters 发现与 CredentialPool 共用 DB 路径 |

### aiPlat-management/frontend/src/components/Builder/RunEventTimeline.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-system | §二十四 编排系统 | 4 | RunEventTimeline UI |

### aiPlat-management/management/auth.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| management-and-quality | §二十五 管理 & 质量 | 119 | management_api_token / assert_bind_allowed 鉴权 |

### aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 571 | FDE 能力自描述 |

### aiPlat-platform/apps/fde/api/router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 2 | FDE 路由挂载 |

### core/api/core_facade.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| arena-and-scheduling | §二十 Arena & 调度 | 6 | CoreFacade 暴露 DarwinArena |
| skill-system | §六 Skill 系统 | 213 | CoreFacade 暴露 skill compat |
| evaluation-system | §十三 评估系统 | 646 | CoreFacade 暴露 m2 deferred estimate |
| diagnosis-system | §十三-b 诊断系统 | 20 | CoreFacade 暴露 get_diagnosis_store |
| tool-ecosystem | §十六 工具生态 | 73 | CoreFacade 暴露 tool compat |
| a2a-protocol | §十四附 A2A 协议 | 2 | CoreFacade 再导出 A2A 能力 |

### core/api/routers/adapters.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| runtime-intervention | §十九 运行时干预 | 66 | /model-override 端点 |

### core/api/routers/diagnostics.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| observability | §八 可观测性 | 23 | 诊断 API 消费 observability contract / AgentEventIngress |
| runtime-intervention | §十九 运行时干预 | 66 | adoption-metrics 附带 Howl 干预次数 |

### core/api/routers/memory.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 59 | 全量 REST 端点 |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | GET/PUT /memory/rules |

### core/api/routers/runs.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-system | §二十四 编排系统 | 4 | list_run_events REST |

### core/api/routers/wiki.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 571 | Wiki CRUD + index + ingest 端点 |
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | /wiki/index-md + /ingest/url 端点 |

### core/api/routers/wiki_ontology_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 571 | 本体引擎 REST API |

### core/api/routers/workspace_tools.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| tool-ecosystem | §十六 工具生态 | 73 | workspace tools 跑 tool compat |

### core/apps/agents/discovery.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| a2a-protocol | §十四附 A2A 协议 | 2 | AgentDiscovery 实现/导出 |

### core/apps/agents/materials_chat.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 10 | CRAG + HyDE + RRF 自身 |

### core/apps/mcp/runtime.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 14 | MCP runtime 消费 finalize_mcp_compat / mark_mcp_connection |

### core/harness/coordination/swarm_broker.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-layer | §二十六 编排层 | 5 | 动态组队 |

### core/harness/evolution_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-operations | §十 部署与运维 | 3 | self-harness cycle |
| fine-tuning-system | §十七 微调系统 | 2 | nightly LoRA trigger |

### core/harness/execution/pipeline_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 642 | 自身消费 PipelineStageConfig + StageRunner |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | _run_moa 路由模式 |
| model-infrastructure | §九 模型基础设施 | 7 | Pipeline 阶段模型选择 |
| memory-subsystem | §二 记忆子系统 | 59 | _crystallize_skill → save_task_skill |
| orchestration-layer | §二十六 编排层 | 5 | Pipeline → Swarm/Debate/Roundtable/MoA dispatch |
| extension-and-learning | §十一 扩展与学习 | 10 | Pipeline 故障→StrategySearchEngine |

### core/harness/integration/agent.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| gate-system | §十二 Gate 系统 | 153 | Agent 集成路径消费 ErrorTranslator / CompletionChecklistGate |

### core/harness/interfaces/loop.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 642 | ReActLoop 运行时 |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | ReActLoop MoA interception |
| memory-subsystem | §二 记忆子系统 | 59 | build_context() + save_interaction() 调用 |

### core/harness/knowledge/context_bus.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 571 | 10层上下文注入 |

### core/harness/memory/manager.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| hermes-compression | §三十二 Hermes压缩对标 | 3 | build_context → normalize_roles + reminder dict injection |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | save_interaction 过滤逻辑 |
| memory-white-boxing | §二十八 记忆系统白盒化 | 5 | MemoryManager 混入 LongTermMemoryMixin |
| knowledge-infrastructure | §四附 知识基础设施 | 5 | build_context 注入 ContextBus |

### core/harness/memory/reminders.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| hermes-compression | §三十二 Hermes压缩对标 | 3 | 结构化返回 dict 而非裸字符串 |

### core/harness/multimodal/integrator.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| document-intelligence | §十五 文档智能 | 3 | 多模态集成消费 VideoParser |

### core/harness/optimization/goal_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _execute_business_objective |
| extension-and-learning | §十一 扩展与学习 | 10 | GoalExecutor 启动 + 执行循环 |
| deploy-and-canary | §十八 部署与灰度 | 3 | tool_gap → DeployEngine.deploy |

### core/harness/optimization/goal_generator.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _scan_business_objectives |

### core/harness/optimization/tool_bootstrap.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 7 | ToolBootstrap 模型选择 |
| extension-and-learning | §十一 扩展与学习 | 10 | ToolBootstrap 自举工具创建 |
| deploy-and-canary | §十八 部署与灰度 | 3 | _trigger_deploy |

### core/harness/scheduler/wake_scheduler.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _try_decompose_pending |

### core/harness/syscalls/llm.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 7 | sys_llm_generate → best_model_for_purpose |

### core/harness/syscalls/moa_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 7 | MoA 引擎多模型路由 |

### core/harness/syscalls/retrieval.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 10 | 检索路由 + 多路融合 |

### core/harness/utils/model_injection.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | is_moa_session/get_moa_preset + override filtering |
| infra-infrastructure | §二十二 Infra 基础设施 | 6 | ModelManager 缓存 |

### core/management/asset_installer.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 333 | 安装/升级时跑 agent compat 门禁 |

### core/management/skill_installer.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 213 | skill install 跑 finalize_skill_compat |

### core/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| arena-and-scheduling | §二十 Arena & 调度 | 6 | server 挂载 VoiceLoopTool |
| core-api-unified-entry | §二十三 核心API统一入口 | 2 | Core server 入口挂载 CoreFacade |
| deploy-and-operations | §十 部署与运维 | 3 | 启动时挂载 cron + WakeScheduler |
| extension-and-learning | §十一 扩展与学习 | 10 | GoalExecutor + WakeScheduler 启动 |

### core/services/execution_store/__init__.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| platform-governance | §二十一 平台治理 | 14 | default_execution_db_path 出口 |
| memory-white-boxing | §二十八 记忆系统白盒化 | 5 | execution_store 组装 LTM |

## Capability-to-Consumer Impact

### §十四附 A2A 协议 (2 caps)

- **core/apps/agents/discovery.py** — AgentDiscovery 实现/导出
- **core/api/core_facade.py** — CoreFacade 再导出 A2A 能力

### §五 Agent 系统 (333 caps)

- **core/management/asset_installer.py** — 安装/升级时跑 agent compat 门禁

### §三十一 AI知识层增强 (3 caps)

- **core/api/routers/wiki.py** — /wiki/index-md + /ingest/url 端点

### §二十 Arena & 调度 (6 caps)

- **core/api/core_facade.py** — CoreFacade 暴露 DarwinArena
- **core/server.py** — server 挂载 VoiceLoopTool

### §二十三 核心API统一入口 (2 caps)

- **aiPlat-platform/apps/fde/api/router.py** — FDE 路由挂载
- **core/server.py** — Core server 入口挂载 CoreFacade

### §十八 部署与灰度 (3 caps)

- **core/harness/optimization/goal_executor.py** — tool_gap → DeployEngine.deploy
- **core/harness/optimization/tool_bootstrap.py** — _trigger_deploy

### §十 部署与运维 (3 caps)

- **core/server.py** — 启动时挂载 cron + WakeScheduler
- **core/harness/evolution_engine.py** — self-harness cycle

### §十三-b 诊断系统 (20 caps)

- **core/api/core_facade.py** — CoreFacade 暴露 get_diagnosis_store

### §十五 文档智能 (3 caps)

- **core/harness/multimodal/integrator.py** — 多模态集成消费 VideoParser

### §十三 评估系统 (646 caps)

- **core/api/core_facade.py** — CoreFacade 暴露 m2 deferred estimate

### §十一 扩展与学习 (10 caps)

- **core/harness/optimization/goal_executor.py** — GoalExecutor 启动 + 执行循环
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 自举工具创建
- **core/harness/execution/pipeline_engine.py** — Pipeline 故障→StrategySearchEngine
- **core/server.py** — GoalExecutor + WakeScheduler 启动

### §十七 微调系统 (2 caps)

- **core/harness/evolution_engine.py** — nightly LoRA trigger

### §十二 Gate 系统 (153 caps)

- **core/harness/integration/agent.py** — Agent 集成路径消费 ErrorTranslator / CompletionChecklistGate

### §一 Harness 执行引擎 (642 caps)

- **core/harness/execution/pipeline_engine.py** — 自身消费 PipelineStageConfig + StageRunner
- **core/harness/interfaces/loop.py** — ReActLoop 运行时

### §三十二 Hermes压缩对标 (3 caps)

- **core/harness/memory/manager.py** — build_context → normalize_roles + reminder dict injection
- **core/harness/memory/reminders.py** — 结构化返回 dict 而非裸字符串

### §二十二 Infra 基础设施 (6 caps)

- **core/harness/utils/model_injection.py** — ModelManager 缓存
- **aiPlat-infra/infra/management/model/config_loader.py** — adapters 发现与 CredentialPool 共用 DB 路径

### §三 知识引擎（本体） (571 caps)

- **core/api/routers/wiki.py** — Wiki CRUD + index + ingest 端点
- **core/api/routers/wiki_ontology_engine.py** — 本体引擎 REST API
- **core/harness/knowledge/context_bus.py** — 10层上下文注入
- **aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py** — FDE 能力自描述

### §四附 知识基础设施 (5 caps)

- **core/harness/memory/manager.py** — build_context 注入 ContextBus

### §二十七 L6 自主能力 (5 caps)

- **core/harness/optimization/goal_generator.py** — _scan_business_objectives
- **core/harness/optimization/goal_executor.py** — _execute_business_objective
- **core/harness/scheduler/wake_scheduler.py** — _try_decompose_pending

### §二十五 管理 & 质量 (119 caps)

- **aiPlat-management/management/auth.py** — management_api_token / assert_bind_allowed 鉴权

### §十四 MCP 协议 (14 caps)

- **core/apps/mcp/runtime.py** — MCP runtime 消费 finalize_mcp_compat / mark_mcp_connection

### §二十九 记忆运行时过滤 (2 caps)

- **core/harness/memory/manager.py** — save_interaction 过滤逻辑
- **core/api/routers/memory.py** — GET/PUT /memory/rules

### §二 记忆子系统 (59 caps)

- **core/harness/interfaces/loop.py** — build_context() + save_interaction() 调用
- **core/harness/execution/pipeline_engine.py** — _crystallize_skill → save_task_skill
- **core/api/routers/memory.py** — 全量 REST 端点

### §二十八 记忆系统白盒化 (5 caps)

- **core/harness/memory/manager.py** — MemoryManager 混入 LongTermMemoryMixin
- **core/services/execution_store/__init__.py** — execution_store 组装 LTM

### §三十 MoA 多模型推理 (5 caps)

- **core/harness/interfaces/loop.py** — ReActLoop MoA interception
- **core/harness/execution/pipeline_engine.py** — _run_moa 路由模式
- **core/harness/utils/model_injection.py** — is_moa_session/get_moa_preset + override filtering

### §九 模型基础设施 (7 caps)

- **core/harness/syscalls/llm.py** — sys_llm_generate → best_model_for_purpose
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 模型选择
- **core/harness/syscalls/moa_executor.py** — MoA 引擎多模型路由
- **core/harness/execution/pipeline_engine.py** — Pipeline 阶段模型选择

### §八 可观测性 (23 caps)

- **core/api/routers/diagnostics.py** — 诊断 API 消费 observability contract / AgentEventIngress

### §二十六 编排层 (5 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline → Swarm/Debate/Roundtable/MoA dispatch
- **core/harness/coordination/swarm_broker.py** — 动态组队

### §二十四 编排系统 (4 caps)

- **core/api/routers/runs.py** — list_run_events REST
- **aiPlat-management/frontend/src/components/Builder/RunEventTimeline.tsx** — RunEventTimeline UI

### §二十一 平台治理 (14 caps)

- **core/services/execution_store/__init__.py** — default_execution_db_path 出口

### §四 RAG 检索 (10 caps)

- **core/apps/agents/materials_chat.py** — CRAG + HyDE + RRF 自身
- **core/harness/syscalls/retrieval.py** — 检索路由 + 多路融合

### §十九 运行时干预 (66 caps)

- **core/api/routers/adapters.py** — /model-override 端点
- **core/api/routers/diagnostics.py** — adoption-metrics 附带 Howl 干预次数

### §六 Skill 系统 (213 caps)

- **core/management/skill_installer.py** — skill install 跑 finalize_skill_compat
- **core/api/core_facade.py** — CoreFacade 暴露 skill compat

### §十六 工具生态 (73 caps)

- **core/api/routers/workspace_tools.py** — workspace tools 跑 tool compat
- **core/api/core_facade.py** — CoreFacade 暴露 tool compat

