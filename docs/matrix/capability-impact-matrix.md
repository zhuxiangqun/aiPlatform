# Capability Impact Matrix

> Auto-generated from `capability_registry.yaml`
> Version: 1.1.0 | 34 domains | 1041 capabilities

## Consumer-to-Capability Dependencies

### aiPlat-infra/infra/management/model/config_loader.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 4 | adapters 发现与 CredentialPool 共用 DB 路径 |

### aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | MoA 卡片交互 |
| model-infrastructure | §九 模型基础设施 | 5 | T1-T5 前端展示 |

### aiPlat-management/frontend/src/pages/Core/Memory/Memory.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-white-boxing | §二十八 记忆系统白盒化 | 5 | 记忆管理页面 |

### aiPlat-management/frontend/src/pages/Diagnostics

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| management-and-quality | §二十五 管理 & 质量 | 37 | 诊断仪表盘 |
| observability | §八 可观测性 | 21 | 诊断仪表盘 |

### aiPlat-management/frontend/src/pages/Infra

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 4 | Infra 管理前端 |

### aiPlat-platform/apps/eval/api/arena_wiring.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| arena-and-scheduling | §二十 Arena & 调度 | 6 | P0-B3 arena/wake-agent REST 端点 |

### aiPlat-platform/apps/fde/api/fde.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-canary | §十八 部署与灰度 | 3 | FDE canary 端点 |

### aiPlat-platform/apps/fde/api/fde_ask.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 6 | FDE 追问 → 检索增强 |

### aiPlat-platform/apps/fde/api/fde_dashboard_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 7 | L6 记忆指标展示 |
| platform-governance | §二十一 平台治理 | 6 | 仪表盘治理指标 |
| l6-autonomy | §二十七 L6 自主能力 | 5 | _get_goal_decomposition_stats |

### aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | FDE 能力自描述 |

### aiPlat-platform/apps/fde/api/fde_pipeline.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 158 | FDE Pipeline 状态查询 |

### aiPlat-platform/apps/fde/api/fde_quality_summary.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| evaluation-system | §十三 评估系统 | 5 | FDE 质量摘要 |

### aiPlat-platform/apps/fde/api/router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 2 | FDE 路由挂载 |

### aiPlat-platform/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 2 | Platform server 入口 |

### core/api/routers/adapters.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | /model-override/moa 端点 |
| runtime-intervention | §十九 运行时干预 | 4 | /model-override 端点 |

### core/api/routers/agents.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 150 | Agent REST 端点 |

### core/api/routers/builder_project_service.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 158 | PipelineEngine 调度入口 |

### core/api/routers/engine_skills.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 136 | Skill REST 端点 |

### core/api/routers/mcp.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 3 | MCP REST 端点 |

### core/api/routers/memory.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 7 | 全量 REST 端点 |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | GET/PUT /memory/rules |
| memory-white-boxing | §二十八 记忆系统白盒化 | 5 | 全量记忆 REST 端点 |

### core/api/routers/pipeline_execution.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-system | §二十四 编排系统 | 6 | fork/forks 端点经 CoreFacade 取 store |

### core/api/routers/wiki.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | Wiki CRUD + index + ingest 端点 |
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | /wiki/index-md + /ingest/url 端点 |
| document-intelligence | §十五 文档智能 | 4 | Upload/ingest 端点 |

### core/api/routers/wiki_ontology_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | 本体引擎 REST API |

### core/api/routers/workspace_skills.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 136 | auto-fill + create-dialog HTTP |

### core/apps/agents/materials_chat.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 6 | CRAG + HyDE + RRF 自身 |

### core/apps/agents/multi_agent.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| a2a-protocol | §十四附 A2A 协议 | 2 | MultiAgent 通信 |

### core/apps/builder/builder_project_service.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 150 | Builder 创建 Agent |

### core/apps/mcp/adapter.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| tool-ecosystem | §十六 工具生态 | 58 | MCPToolAdapter → BaseTool |

### core/apps/mcp/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 3 | MCP server lifecycle |

### core/engine/skills/autoreview/handler.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| skill-system | §六 Skill 系统 | 136 | autoreview Skill handler |

### core/harness/coordination/swarm_broker.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| arena-and-scheduling | §二十 Arena & 调度 | 6 | SwarmBroker 蜂群协作 |
| orchestration-layer | §二十六 编排层 | 5 | 动态组队 |
| a2a-protocol | §十四附 A2A 协议 | 2 | SwarmBroker agent discovery |

### core/harness/evolution_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-operations | §十 部署与运维 | 3 | self-harness cycle |
| fine-tuning-system | §十七 微调系统 | 2 | nightly LoRA trigger |

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
| harness-execution-engine | §一 Harness 执行引擎 | 158 | 自身消费 PipelineStageConfig + StageRunner |
| security-and-governance | §七 安全与治理 | 8 | HITL → PolicyGate + ApprovalGate |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | _run_moa 路由模式 |
| model-infrastructure | §九 模型基础设施 | 5 | Pipeline 阶段模型选择 |
| memory-subsystem | §二 记忆子系统 | 7 | _crystallize_skill → save_task_skill |
| arena-and-scheduling | §二十 Arena & 调度 | 6 | Pipeline routing_mode dispatch |
| management-and-quality | §二十五 管理 & 质量 | 37 | Pipeline 质量评分 |
| orchestration-layer | §二十六 编排层 | 5 | Pipeline → Swarm/Debate/Roundtable/MoA dispatch |
| orchestration-system | §二十四 编排系统 | 6 | Pipeline 编排 |
| agent-system | §五 Agent 系统 | 150 | Pipeline 调度 Agent |
| observability | §八 可观测性 | 21 | Pipeline trace 事件 |
| skill-system | §六 Skill 系统 | 136 | Pipeline 调用 Skill |
| extension-and-learning | §十一 扩展与学习 | 10 | Pipeline 故障→StrategySearchEngine |
| evaluation-system | §十三 评估系统 | 5 | Pipeline 质量评分 |
| gate-system | §十二 Gate 系统 | 133 | Pipeline 阶段 Gate 检查 |
| knowledge-infrastructure | §四附 知识基础设施 | 4 | RunContext 运行时上下文 |

### core/harness/infrastructure/infra_llm_adapter.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 4 | LLM 适配器 → infra |

### core/harness/infrastructure/integration.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| gate-system | §十二 Gate 系统 | 133 | 8 Gate 统一出口 |

### core/harness/interfaces/loop.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 158 | ReActLoop 运行时 |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | ReActLoop MoA interception |
| memory-subsystem | §二 记忆子系统 | 7 | build_context() + save_interaction() 调用 |

### core/harness/knowledge/context_bus.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | 10层上下文注入 |

### core/harness/knowledge/domain_maturity.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | 域成熟度评分 |

### core/harness/knowledge/domain_router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 6 | 域分类 → 检索范围确定 |

### core/harness/knowledge/knowledge_synthesis.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | KnowledgeSynthesizer 合成 Wiki 页 |

### core/harness/knowledge/ontology_completeness.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | OCS 本体完整性六维评分 |

### core/harness/knowledge/seci_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-infrastructure | §四附 知识基础设施 | 4 | SECI 消费 KnowledgeSynthesizer |

### core/harness/memory/manager.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | build_context 注入 brand_rules |
| hermes-compression | §三十二 Hermes压缩对标 | 3 | build_context → normalize_roles + reminder dict injection |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | save_interaction 过滤逻辑 |
| extension-and-learning | §十一 扩展与学习 | 10 | build_context → SharedKnowledgePool 注入 |
| knowledge-infrastructure | §四附 知识基础设施 | 4 | build_context 注入 ContextBus |

### core/harness/memory/reminders.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| hermes-compression | §三十二 Hermes压缩对标 | 3 | 结构化返回 dict 而非裸字符串 |

### core/harness/ontology_engine/engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| platform-governance | §二十一 平台治理 | 6 | 本体引擎治理 |
| document-intelligence | §十五 文档智能 | 4 | OntologyEngine 文档输入 |

### core/harness/optimization/goal_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _execute_business_objective |
| orchestration-layer | §二十六 编排层 | 5 | Goal 分解后并行执行 |
| extension-and-learning | §十一 扩展与学习 | 10 | GoalExecutor 启动 + 执行循环 |
| deploy-and-canary | §十八 部署与灰度 | 3 | tool_gap → DeployEngine.deploy |

### core/harness/optimization/goal_generator.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _scan_business_objectives |
| fine-tuning-system | §十七 微调系统 | 2 | 微调缺口扫描 |

### core/harness/optimization/tool_bootstrap.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 5 | ToolBootstrap 模型选择 |
| skill-system | §六 Skill 系统 | 136 | ToolBootstrap → SkillRegistry.register |
| extension-and-learning | §十一 扩展与学习 | 10 | ToolBootstrap 自举工具创建 |
| deploy-and-canary | §十八 部署与灰度 | 3 | _trigger_deploy |

### core/harness/scheduler/wake_scheduler.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| l6-autonomy | §二十七 L6 自主能力 | 5 | _try_decompose_pending |

### core/harness/syscalls/llm.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 8 | _guard_messages → PII masking |
| model-infrastructure | §九 模型基础设施 | 5 | sys_llm_generate → best_model_for_purpose |
| runtime-intervention | §十九 运行时干预 | 4 | 最佳模型选择 |

### core/harness/syscalls/moa_executor.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| model-infrastructure | §九 模型基础设施 | 5 | MoA 引擎多模型路由 |

### core/harness/syscalls/retrieval.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 230 | GraphIndex 遍历检索 |
| memory-subsystem | §二 记忆子系统 | 7 | 语义记忆检索 |
| rag-retrieval | §四 RAG 检索 | 6 | 检索路由 + 多路融合 |

### core/harness/syscalls/skill.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 8 | sys_skill_call → PolicyGate |
| skill-system | §六 Skill 系统 | 136 | sys_skill_call |

### core/harness/syscalls/tool.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| security-and-governance | §七 安全与治理 | 8 | sys_tool_call → PolicyGate.check_tool |
| observability | §八 可观测性 | 21 | 工具调用审计 |
| tool-ecosystem | §十六 工具生态 | 58 | sys_tool_call → ToolRegistry |

### core/harness/utils/model_injection.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | is_moa_session/get_moa_preset + override filtering |
| infra-infrastructure | §二十二 Infra 基础设施 | 4 | ModelManager 缓存 |

### core/server.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| platform-governance | §二十一 平台治理 | 6 | Governance cron 定时任务 |
| l6-autonomy | §二十七 L6 自主能力 | 5 | DiscoveryListener 启动 |
| deploy-and-operations | §十 部署与运维 | 3 | 启动时挂载 cron + WakeScheduler |
| extension-and-learning | §十一 扩展与学习 | 10 | GoalExecutor + WakeScheduler 启动 |
| gate-system | §十二 Gate 系统 | 133 | BackpressureMiddleware 挂载 + backpressure_stats 诊断 |

## Capability-to-Consumer Impact

### §十四附 A2A 协议 (2 caps)

- **core/apps/agents/multi_agent.py** — MultiAgent 通信
- **core/harness/coordination/swarm_broker.py** — SwarmBroker agent discovery

### §五 Agent 系统 (150 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 调度 Agent
- **core/apps/builder/builder_project_service.py** — Builder 创建 Agent
- **core/api/routers/agents.py** — Agent REST 端点

### §三十一 AI知识层增强 (3 caps)

- **core/api/routers/wiki.py** — /wiki/index-md + /ingest/url 端点
- **core/harness/memory/manager.py** — build_context 注入 brand_rules

### §二十 Arena & 调度 (6 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline routing_mode dispatch
- **core/harness/coordination/swarm_broker.py** — SwarmBroker 蜂群协作
- **aiPlat-platform/apps/eval/api/arena_wiring.py** — P0-B3 arena/wake-agent REST 端点

### §二十三 核心API统一入口 (2 caps)

- **aiPlat-platform/apps/fde/api/router.py** — FDE 路由挂载
- **aiPlat-platform/server.py** — Platform server 入口

### §十八 部署与灰度 (3 caps)

- **core/harness/optimization/goal_executor.py** — tool_gap → DeployEngine.deploy
- **core/harness/optimization/tool_bootstrap.py** — _trigger_deploy
- **aiPlat-platform/apps/fde/api/fde.py** — FDE canary 端点

### §十 部署与运维 (3 caps)

- **core/server.py** — 启动时挂载 cron + WakeScheduler
- **core/harness/evolution_engine.py** — self-harness cycle

### §十五 文档智能 (4 caps)

- **core/harness/ontology_engine/engine.py** — OntologyEngine 文档输入
- **core/api/routers/wiki.py** — Upload/ingest 端点

### §十三 评估系统 (5 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 质量评分
- **aiPlat-platform/apps/fde/api/fde_quality_summary.py** — FDE 质量摘要

### §十一 扩展与学习 (10 caps)

- **core/harness/optimization/goal_executor.py** — GoalExecutor 启动 + 执行循环
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 自举工具创建
- **core/harness/execution/pipeline_engine.py** — Pipeline 故障→StrategySearchEngine
- **core/server.py** — GoalExecutor + WakeScheduler 启动
- **core/harness/memory/manager.py** — build_context → SharedKnowledgePool 注入

### §十七 微调系统 (2 caps)

- **core/harness/evolution_engine.py** — nightly LoRA trigger
- **core/harness/optimization/goal_generator.py** — 微调缺口扫描

### §十二 Gate 系统 (133 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 阶段 Gate 检查
- **core/harness/infrastructure/integration.py** — 8 Gate 统一出口
- **core/server.py** — BackpressureMiddleware 挂载 + backpressure_stats 诊断

### §一 Harness 执行引擎 (158 caps)

- **core/api/routers/builder_project_service.py** — PipelineEngine 调度入口
- **core/harness/execution/pipeline_engine.py** — 自身消费 PipelineStageConfig + StageRunner
- **core/harness/interfaces/loop.py** — ReActLoop 运行时
- **aiPlat-platform/apps/fde/api/fde_pipeline.py** — FDE Pipeline 状态查询

### §三十二 Hermes压缩对标 (3 caps)

- **core/harness/execution/loop/compressor.py** — 5-stage compression pipeline → micro_compress
- **core/harness/memory/manager.py** — build_context → normalize_roles + reminder dict injection
- **core/harness/memory/reminders.py** — 结构化返回 dict 而非裸字符串

### §二十二 Infra 基础设施 (4 caps)

- **core/harness/infrastructure/infra_llm_adapter.py** — LLM 适配器 → infra
- **core/harness/utils/model_injection.py** — ModelManager 缓存
- **aiPlat-management/frontend/src/pages/Infra** — Infra 管理前端
- **aiPlat-infra/infra/management/model/config_loader.py** — adapters 发现与 CredentialPool 共用 DB 路径

### §三 知识引擎（本体） (230 caps)

- **core/api/routers/wiki.py** — Wiki CRUD + index + ingest 端点
- **core/api/routers/wiki_ontology_engine.py** — 本体引擎 REST API
- **core/harness/syscalls/retrieval.py** — GraphIndex 遍历检索
- **core/harness/knowledge/context_bus.py** — 10层上下文注入
- **core/harness/knowledge/knowledge_synthesis.py** — KnowledgeSynthesizer 合成 Wiki 页
- **aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py** — FDE 能力自描述
- **core/harness/knowledge/domain_maturity.py** — 域成熟度评分
- **core/harness/knowledge/ontology_completeness.py** — OCS 本体完整性六维评分

### §四附 知识基础设施 (4 caps)

- **core/harness/knowledge/seci_engine.py** — SECI 消费 KnowledgeSynthesizer
- **core/harness/memory/manager.py** — build_context 注入 ContextBus
- **core/harness/execution/pipeline_engine.py** — RunContext 运行时上下文

### §二十七 L6 自主能力 (5 caps)

- **core/harness/optimization/goal_generator.py** — _scan_business_objectives
- **core/harness/optimization/goal_executor.py** — _execute_business_objective
- **core/harness/scheduler/wake_scheduler.py** — _try_decompose_pending
- **core/server.py** — DiscoveryListener 启动
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — _get_goal_decomposition_stats

### §二十五 管理 & 质量 (37 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 质量评分
- **aiPlat-management/frontend/src/pages/Diagnostics** — 诊断仪表盘

### §十四 MCP 协议 (3 caps)

- **core/apps/mcp/server.py** — MCP server lifecycle
- **core/api/routers/mcp.py** — MCP REST 端点

### §二十九 记忆运行时过滤 (2 caps)

- **core/harness/memory/manager.py** — save_interaction 过滤逻辑
- **core/api/routers/memory.py** — GET/PUT /memory/rules

### §二 记忆子系统 (7 caps)

- **core/harness/interfaces/loop.py** — build_context() + save_interaction() 调用
- **core/harness/execution/pipeline_engine.py** — _crystallize_skill → save_task_skill
- **core/api/routers/memory.py** — 全量 REST 端点
- **core/harness/syscalls/retrieval.py** — 语义记忆检索
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — L6 记忆指标展示

### §二十八 记忆系统白盒化 (5 caps)

- **core/api/routers/memory.py** — 全量记忆 REST 端点
- **aiPlat-management/frontend/src/pages/Core/Memory/Memory.tsx** — 记忆管理页面

### §三十 MoA 多模型推理 (5 caps)

- **core/harness/interfaces/loop.py** — ReActLoop MoA interception
- **core/harness/execution/pipeline_engine.py** — _run_moa 路由模式
- **core/harness/utils/model_injection.py** — is_moa_session/get_moa_preset + override filtering
- **core/api/routers/adapters.py** — /model-override/moa 端点
- **aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx** — MoA 卡片交互
- **core/harness/execution/loop/command_parser.py** — /moa --preset 命令解析

### §九 模型基础设施 (5 caps)

- **core/harness/syscalls/llm.py** — sys_llm_generate → best_model_for_purpose
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap 模型选择
- **core/harness/syscalls/moa_executor.py** — MoA 引擎多模型路由
- **core/harness/execution/pipeline_engine.py** — Pipeline 阶段模型选择
- **aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx** — T1-T5 前端展示

### §八 可观测性 (21 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline trace 事件
- **core/harness/syscalls/tool.py** — 工具调用审计
- **aiPlat-management/frontend/src/pages/Diagnostics** — 诊断仪表盘

### §二十六 编排层 (5 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline → Swarm/Debate/Roundtable/MoA dispatch
- **core/harness/coordination/swarm_broker.py** — 动态组队
- **core/harness/optimization/goal_executor.py** — Goal 分解后并行执行

### §二十四 编排系统 (6 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 编排
- **core/api/routers/pipeline_execution.py** — fork/forks 端点经 CoreFacade 取 store

### §二十一 平台治理 (6 caps)

- **core/server.py** — Governance cron 定时任务
- **core/harness/ontology_engine/engine.py** — 本体引擎治理
- **aiPlat-platform/apps/fde/api/fde_dashboard_v2.py** — 仪表盘治理指标

### §四 RAG 检索 (6 caps)

- **core/apps/agents/materials_chat.py** — CRAG + HyDE + RRF 自身
- **core/harness/syscalls/retrieval.py** — 检索路由 + 多路融合
- **core/harness/knowledge/domain_router.py** — 域分类 → 检索范围确定
- **aiPlat-platform/apps/fde/api/fde_ask.py** — FDE 追问 → 检索增强

### §十九 运行时干预 (4 caps)

- **core/api/routers/adapters.py** — /model-override 端点
- **core/harness/syscalls/llm.py** — 最佳模型选择

### §七 安全与治理 (8 caps)

- **core/harness/syscalls/tool.py** — sys_tool_call → PolicyGate.check_tool
- **core/harness/syscalls/skill.py** — sys_skill_call → PolicyGate
- **core/harness/execution/pipeline_engine.py** — HITL → PolicyGate + ApprovalGate
- **core/harness/syscalls/llm.py** — _guard_messages → PII masking

### §六 Skill 系统 (136 caps)

- **core/harness/execution/pipeline_engine.py** — Pipeline 调用 Skill
- **core/harness/syscalls/skill.py** — sys_skill_call
- **core/harness/optimization/tool_bootstrap.py** — ToolBootstrap → SkillRegistry.register
- **core/api/routers/engine_skills.py** — Skill REST 端点
- **core/engine/skills/autoreview/handler.py** — autoreview Skill handler
- **core/api/routers/workspace_skills.py** — auto-fill + create-dialog HTTP

### §十六 工具生态 (58 caps)

- **core/harness/syscalls/tool.py** — sys_tool_call → ToolRegistry
- **core/apps/mcp/adapter.py** — MCPToolAdapter → BaseTool

