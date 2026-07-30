# Capability Impact Matrix

> Auto-generated from `capability_registry.yaml`
> Version: 1.0.0 | 32 domains | （见 AIPLAT_CAPABILITIES.md 当前计数）capabilities

## Consumer-to-Capability Dependencies

### aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | MoA 卡片交互 |
| model-infrastructure | §九 模型基础设施 | 27 | T1-T5 前端展示 |

### aiPlat-management/frontend/src/pages/Core/Memory/Memory.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-white-boxing | §二十八 记忆系统白盒化 | 7 | 记忆管理页面 |

### aiPlat-management/frontend/src/pages/Diagnostics

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| management-and-quality | §二十五 管理 & 质量 | 21 | 诊断仪表盘 |
| observability | §八 可观测性 | 16 | 诊断仪表盘 |

### aiPlat-management/frontend/src/pages/Infra

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 11 | Infra 管理前端 |

### aiPlat-platform/apps/fde/api/fde.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-canary | §十八 部署与灰度 | 4 | FDE canary 端点 |

### aiPlat-platform/apps/fde/api/fde_ask.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 40 | FDE 追问 → 检索增强 |

### aiPlat-platform/apps/fde/api/fde_dashboard_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 31 | L6 记忆指标展示 |
| platform-governance | §二十一 平台治理 | 59 | 仪表盘治理指标 |
| l6-autonomy | §二十七 L6 自主能力 | 8 | _get_goal_decomposition_stats |

### aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | FDE 能力自描述 |

### aiPlat-platform/apps/fde/api/fde_pipeline.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 34 | FDE Pipeline 状态查询 |

### aiPlat-platform/apps/fde/api/fde_quality_summary.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| evaluation-system | §十三 评估系统 | 13 | FDE 质量摘要 |

### aiPlat-platform/apps/fde/api/router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 5 | FDE 路由挂载 |

### aiPlat-platform/apps/fde/orchestration/builder.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 34 | FDEBuilderOrch 构建流水线 |
| orchestration-system | §二十四 编排系统 | 4 | FDEBuilderOrch 编排 |

### aiPlat-platform/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 5 | Platform server 入口 |

### core/api/routers/adapters.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | /model-override/moa 端点 |
| runtime-intervention | §十九 运行时干预 | 2 | /model-override 端点 |

### core/api/routers/agents.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 23 | Agent REST 端点 |

### core/api/routers/builder_project_service.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 34 | PipelineEngine 调度入口 |

### core/api/routers/engine_skills.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 23 | Skill REST 端点 |

### core/api/routers/mcp.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 6 | MCP REST 端点 |

### core/api/routers/memory.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 31 | 全量 REST 端点 |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | GET/PUT /memory/rules |
| memory-white-boxing | §二十八 记忆系统白盒化 | 7 | 全量记忆 REST 端点 |

### core/api/routers/wiki.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | Wiki CRUD + index + ingest 端点 |
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | /wiki/index-md + /ingest/url 端点 |
| document-intelligence | §十五 文档智能 | 24 | Upload/ingest 端点 |

### core/api/routers/wiki_ontology_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | 本体引擎 REST API |

### core/apps/agents/materials_chat.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 40 | CRAG + HyDE + RRF 自身 |

### core/apps/agents/multi_agent.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| a2a-protocol | §十四附 A2A 协议 | 7 | MultiAgent 通信 |

### core/apps/builder/builder_project_service.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 23 | Builder 创建 Agent |

### core/apps/mcp/adapter.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| tool-ecosystem | §十六 工具生态 | 21 | MCPToolAdapter → BaseTool |

### core/apps/mcp/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 6 | MCP server lifecycle |

### core/engine/skills/autoreview/handler.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 23 | autoreview Skill handler |

### core/harness/coordination/swarm_broker.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| arena-and-scheduling | §二十 Arena & 调度 | 4 | SwarmBroker 蜂群协作 |
| orchestration-layer | §二十六 编排层 | 17 | 动态组队 |
| a2a-protocol | §十四附 A2A 协议 | 7 | SwarmBroker agent discovery |

### core/harness/evolution_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-operations | §十 部署与运维 | 17 | self-harness cycle |
| fine-tuning-system | §十七 微调系统 | 12 | nightly LoRA trigger |

### core/harness/execution/loop/command_parser.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | /moa --preset 命令解析 |

### core/harness/execution/loop/compressor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| hermes-compression | §三十二 Hermes压缩对标 | 3 | 5-stage compression pipeline → micro_compress |

### core/harness/execution/pipeline_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 34 | 自身消费 PipelineStageConfig + StageRunner |
| security-and-governance | §七 安全与治理 | 33 | HITL → PolicyGate + ApprovalGate |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | _run_moa 路由模式 |
| model-infrastructure | §九 模型基础设施 | 27 | Pipeline 阶段模型选择 |
| memory-subsystem | §二 记忆子系统 | 31 | _crystallize_skill → save_task_skill |
| arena-and-scheduling | §二十 Arena & 调度 | 4 | Pipeline routing_mode dispatch |
| management-and-quality | §二十五 管理 & 质量 | 21 | Pipeline 质量评分 |
| orchestration-layer | §二十六 编排层 | 17 | Pipeline → Swarm/Debate/Roundtable/MoA dispatch |
| orchestration-system | §二十四 编排系统 | 4 | Pipeline 编排 |
| agent-system | §五 Agent 系统 | 23 | Pipeline 调度 Agent |
| observability | §八 可观测性 | 16 | Pipeline trace 事件 |
| skill-system | §六 Skill 系统 | 23 | Pipeline 调用 Skill |
| extension-and-learning | §十一 扩展与学习 | 79 | Pipeline 故障→StrategySearchEngine |
| evaluation-system | §十三 评估系统 | 13 | Pipeline 质量评分 |
| gate-system | §十二 Gate 系统 | 17 | Pipeline 阶段 Gate 检查 |
| knowledge-infrastructure | §四附 知识基础设施 | 29 | RunContext 运行时上下文 |

### core/harness/infrastructure/infra_llm_adapter.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 11 | LLM 适配器 → infra |

### core/harness/infrastructure/integration.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| gate-system | §十二 Gate 系统 | 17 | 8 Gate 统一出口 |

### core/harness/interfaces/loop.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 34 | ReActLoop 运行时 |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | ReActLoop MoA interception |
| memory-subsystem | §二 记忆子系统 | 31 | build_context() + save_interaction() 调用 |

### core/harness/knowledge/context_bus.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | 10层上下文注入 |

### core/harness/knowledge/domain_maturity.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | 域成熟度评分 |

### core/harness/knowledge/domain_router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 40 | 域分类 → 检索范围确定 |

### core/harness/knowledge/knowledge_synthesis.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | KnowledgeSynthesizer 合成 Wiki 页 |

### core/harness/knowledge/seci_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-infrastructure | §四附 知识基础设施 | 29 | SECI 消费 KnowledgeSynthesizer |

### core/harness/memory/manager.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | build_context 注入 brand_rules |
| hermes-compression | §三十二 Hermes压缩对标 | 3 | build_context → normalize_roles + reminder dict injection |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | save_interaction 过滤逻辑 |
| extension-and-learning | §十一 扩展与学习 | 79 | build_context → SharedKnowledgePool 注入 |
| knowledge-infrastructure | §四附 知识基础设施 | 29 | build_context 注入 ContextBus |

### core/harness/memory/reminders.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| hermes-compression | §三十二 Hermes压缩对标 | 3 | 结构化返回 dict 而非裸字符串 |

### core/harness/ontology_engine/engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| platform-governance | §二十一 平台治理 | 59 | 本体引擎治理 |
| document-intelligence | §十五 文档智能 | 24 | OntologyEngine 文档输入 |

### core/harness/optimization/goal_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 8 | _execute_business_objective |
| orchestration-layer | §二十六 编排层 | 17 | Goal 分解后并行执行 |
| extension-and-learning | §十一 扩展与学习 | 79 | GoalExecutor 启动 + 执行循环 |
| deploy-and-canary | §十八 部署与灰度 | 4 | tool_gap → DeployEngine.deploy |

### core/harness/optimization/goal_generator.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 8 | _scan_business_objectives |
| fine-tuning-system | §十七 微调系统 | 12 | 微调缺口扫描 |

### core/harness/optimization/tool_bootstrap.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 27 | ToolBootstrap 模型选择 |
| skill-system | §六 Skill 系统 | 23 | ToolBootstrap → SkillRegistry.register |
| extension-and-learning | §十一 扩展与学习 | 79 | ToolBootstrap 自举工具创建 |
| deploy-and-canary | §十八 部署与灰度 | 4 | _trigger_deploy |

### core/harness/scheduler/wake_scheduler.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 8 | _try_decompose_pending |

### core/harness/syscalls/llm.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 33 | _guard_messages → PII masking |
| model-infrastructure | §九 模型基础设施 | 27 | sys_llm_generate → best_model_for_purpose |
| runtime-intervention | §十九 运行时干预 | 2 | 最佳模型选择 |

### core/harness/syscalls/moa_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 27 | MoA 引擎多模型路由 |

### core/harness/syscalls/retrieval.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 113 | GraphIndex 遍历检索 |
| memory-subsystem | §二 记忆子系统 | 31 | 语义记忆检索 |
| rag-retrieval | §四 RAG 检索 | 40 | 检索路由 + 多路融合 |

### core/harness/syscalls/skill.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 33 | sys_skill_call → PolicyGate |
| skill-system | §六 Skill 系统 | 23 | sys_skill_call |

### core/harness/syscalls/tool.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 33 | sys_tool_call → PolicyGate.check_tool |
| observability | §八 可观测性 | 16 | 工具调用审计 |
| tool-ecosystem | §十六 工具生态 | 21 | sys_tool_call → ToolRegistry |

### core/harness/utils/model_injection.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | is_moa_session/get_moa_preset + override filtering |
| infra-infrastructure | §二十二 Infra 基础设施 | 11 | ModelManager 缓存 |

### core/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| platform-governance | §二十一 平台治理 | 59 | Governance cron 定时任务 |
| l6-autonomy | §二十七 L6 自主能力 | 8 | DiscoveryListener 启动 |
| deploy-and-operations | §十 部署与运维 | 17 | 启动时挂载 cron + WakeScheduler |
| extension-and-learning | §十一 扩展与学习 | 79 | GoalExecutor + WakeScheduler 启动 |

## Capability-to-Consumer Impact

### §十四附 A2A 协议 (7 caps)

- **core/apps/agents/multi_agent.py** — MultiAgent 通信
- **core/harness/coordination/swarm_broker.py** — SwarmBroker agent discovery

### §五 Agent 系统 (23 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 调度 Agent
- **core/apps/builder/builder_project_service.py** — Builder 创建 Agent
- **core/api/routers/agents.py** — Agent REST 端点

### §三十一 AI知识层增强 (3 caps)

- **core/api/routers/wiki.py** — /wiki/index-md + /ingest/url 端点
- **core/harness/memory/manager.py** — build_context 注入 brand_rules

### §二十 Arena & 调度 (4 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline routing_mode dispatch
- **core/harness/coordination/swarm_broker.py** — SwarmBroker 蜂群协作

### §二十三 核心API统一入口 (5 caps)

- **aiPlat-platform/apps/fde/api/router.py** — FDE 路由挂载
- **aiPlat-platform/server.py** — Platform server 入口

### §十八 部署与灰度 (4 caps)

- **core/harness/optimization/goal_executor.py** — tool_gap → DeployEngine.deploy
- **core/harness/optimization/tool_bootstrap.py** — _trigger_deploy
- **aiPlat-platform/apps/fde/api/fde.py** — FDE canary 端点

### §十 部署与运维 (17 caps)

- **core/server.py** — 启动时挂载 cron + WakeScheduler
- **core/harness/evolution_engine.py** — self-harness cycle

### §十五 文档智能 (24 caps)

- **core/harness/ontology_engine/engine.py** — OntologyEngine 文档输入
- **core/api/routers/wiki.py** — Upload/ingest 端点

### §十三 评估系统 (13 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 质量评分
- **aiPlat-platform/apps/fde/api/fde_quality_summary.py** — FDE 质量摘要

### §十一 扩展与学习 (79 caps)

- **core/harness/optimization/goal_executor.py** — GoalExecutor 启动 + 执行循环
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 自举工具创建
- **core/harness/execution/pipeline_engine.py** — Pipeline 故障→StrategySearchEngine
- **core/server.py** — GoalExecutor + WakeScheduler 启动
- **core/harness/memory/manager.py** — build_context → SharedKnowledgePool 注入

### §十七 微调系统 (12 caps)

- **core/harness/evolution_engine.py** — nightly LoRA trigger
- **core/harness/optimization/goal_generator.py** — 微调缺口扫描

### §十二 Gate 系统 (17 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 阶段 Gate 检查
- **core/harness/infrastructure/integration.py** — 8 Gate 统一出口

### §一 Harness 执行引擎 (34 caps)

- **core/api/routers/builder_project_service.py** — PipelineEngine 调度入口
- **core/harness/execution/pipeline_engine.py** — 自身消费 PipelineStageConfig + StageRunner
- **core/harness/interfaces/loop.py** — ReActLoop 运行时
- **aiPlat-platform/apps/fde/api/fde_pipeline.py** — FDE Pipeline 状态查询
- **aiPlat-platform/apps/fde/orchestration/builder.py** — FDEBuilderOrch 构建流水线

### §三十二 Hermes压缩对标 (3 caps)

- **core/harness/execution/loop/compressor.py** — 5-stage compression pipeline → micro_compress
- **core/harness/memory/manager.py** — build_context → normalize_roles + reminder dict injection
- **core/harness/memory/reminders.py** — 结构化返回 dict 而非裸字符串

### §二十二 Infra 基础设施 (11 caps)

- **core/harness/infrastructure/infra_llm_adapter.py** — LLM 适配器 → infra
- **core/harness/utils/model_injection.py** — ModelManager 缓存
- **aiPlat-management/frontend/src/pages/Infra** — Infra 管理前端

### §三 知识引擎（本体） (113 caps)

- **core/api/routers/wiki.py** — Wiki CRUD + index + ingest 端点
- **core/api/routers/wiki_ontology_engine.py** — 本体引擎 REST API
- **core/harness/syscalls/retrieval.py** — GraphIndex 遍历检索
- **core/harness/knowledge/context_bus.py** — 10层上下文注入
- **core/harness/knowledge/knowledge_synthesis.py** — KnowledgeSynthesizer 合成 Wiki 页
- **aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py** — FDE 能力自描述
- **core/harness/knowledge/domain_maturity.py** — 域成熟度评分

### §四附 知识基础设施 (29 caps)

- **core/harness/knowledge/seci_engine.py** — SECI 消费 KnowledgeSynthesizer
- **core/harness/memory/manager.py** — build_context 注入 ContextBus
- **core/harness/execution/pipeline_engine.py** — RunContext 运行时上下文

### §二十七 L6 自主能力 (8 caps)

- **core/harness/optimization/goal_generator.py** — _scan_business_objectives
- **core/harness/optimization/goal_executor.py** — _execute_business_objective
- **core/harness/scheduler/wake_scheduler.py** — _try_decompose_pending
- **core/server.py** — DiscoveryListener 启动
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — _get_goal_decomposition_stats

### §二十五 管理 & 质量 (21 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 质量评分
- **aiPlat-management/frontend/src/pages/Diagnostics** — 诊断仪表盘

### §十四 MCP 协议 (6 caps)

- **core/apps/mcp/server.py** — MCP server lifecycle
- **core/api/routers/mcp.py** — MCP REST 端点

### §二十九 记忆运行时过滤 (2 caps)

- **core/harness/memory/manager.py** — save_interaction 过滤逻辑
- **core/api/routers/memory.py** — GET/PUT /memory/rules

### §二 记忆子系统 (31 caps)

- **core/harness/interfaces/loop.py** — build_context() + save_interaction() 调用
- **core/harness/execution/pipeline_engine.py** — _crystallize_skill → save_task_skill
- **core/api/routers/memory.py** — 全量 REST 端点
- **core/harness/syscalls/retrieval.py** — 语义记忆检索
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — L6 记忆指标展示

### §二十八 记忆系统白盒化 (7 caps)

- **core/api/routers/memory.py** — 全量记忆 REST 端点
- **aiPlat-management/frontend/src/pages/Core/Memory/Memory.tsx** — 记忆管理页面

### §三十 MoA 多模型推理 (5 caps)

- **core/harness/interfaces/loop.py** — ReActLoop MoA interception
- **core/harness/execution/pipeline_engine.py** — _run_moa 路由模式
- **core/harness/utils/model_injection.py** — is_moa_session/get_moa_preset + override filtering
- **core/api/routers/adapters.py** — /model-override/moa 端点
- **aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx** — MoA 卡片交互
- **core/harness/execution/loop/command_parser.py** — /moa --preset 命令解析

### §九 模型基础设施 (27 caps)

- **core/harness/syscalls/llm.py** — sys_llm_generate → best_model_for_purpose
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 模型选择
- **core/harness/syscalls/moa_executor.py** — MoA 引擎多模型路由
- **core/harness/execution/pipeline_engine.py** — Pipeline 阶段模型选择
- **aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx** — T1-T5 前端展示

### §八 可观测性 (16 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline trace 事件
- **core/harness/syscalls/tool.py** — 工具调用审计
- **aiPlat-management/frontend/src/pages/Diagnostics** — 诊断仪表盘

### §二十六 编排层 (17 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline → Swarm/Debate/Roundtable/MoA dispatch
- **core/harness/coordination/swarm_broker.py** — 动态组队
- **core/harness/optimization/goal_executor.py** — Goal 分解后并行执行

### §二十四 编排系统 (4 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 编排
- **aiPlat-platform/apps/fde/orchestration/builder.py** — FDEBuilderOrch 编排

### §二十一 平台治理 (59 caps)

- **core/server.py** — Governance cron 定时任务
- **core/harness/ontology_engine/engine.py** — 本体引擎治理
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — 仪表盘治理指标

### §四 RAG 检索 (40 caps)

- **core/apps/agents/materials_chat.py** — CRAG + HyDE + RRF 自身
- **core/harness/syscalls/retrieval.py** — 检索路由 + 多路融合
- **core/harness/knowledge/domain_router.py** — 域分类 → 检索范围确定
- **aiPlat-platform/apps/fde/api/fde_ask.py** — FDE 追问 → 检索增强

### §十九 运行时干预 (2 caps)

- **core/api/routers/adapters.py** — /model-override 端点
- **core/harness/syscalls/llm.py** — 最佳模型选择

### §七 安全与治理 (33 caps)

- **core/harness/syscalls/tool.py** — sys_tool_call → PolicyGate.check_tool
- **core/harness/syscalls/skill.py** — sys_skill_call → PolicyGate
- **core/harness/execution/pipeline_engine.py** — HITL → PolicyGate + ApprovalGate
- **core/harness/syscalls/llm.py** — _guard_messages → PII masking

### §六 Skill 系统 (23 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 调用 Skill
- **core/harness/syscalls/skill.py** — sys_skill_call
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap → SkillRegistry.register
- **core/api/routers/engine_skills.py** — Skill REST 端点
- **core/engine/skills/autoreview/handler.py** — autoreview Skill handler

### §十六 工具生态 (21 caps)

- **core/harness/syscalls/tool.py** — sys_tool_call → ToolRegistry
- **core/apps/mcp/adapter.py** — MCPToolAdapter → BaseTool

