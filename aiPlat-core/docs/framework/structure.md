# 项目结构（设计真值：以代码事实为准）

> 说明：本文件用于描述 `aiPlat-core/core` 的目录结构。若与代码不一致，以代码事实为准并在此修订。

> aiPlat-core 项目完整目录结构（基于 Harness 操作系统架构）

---

## 一、项目概览

```
aiPlat-core/
├── core/                  # 核心代码
│   ├── __init__.py        # 核心入口
│   ├── exceptions.py      # 异常定义
│   │
│   ├── harness/           # 操作系统层
│   ├── apps/              # 应用层
│   └── adapters/          # 适配器层
│
├── docs/                  # 文档
├── pyproject.toml
└── README.md
```

---

## 二、架构分层

```
┌─────────────────────────────────────────────────────┐
│                    apps/                            │
│              (Agent、Skill、Tool 具体实现)           │
├─────────────────────────────────────────────────────┤
│                  harness/                            │
│              (操作系统层：执行、协调、观测等)         │
├─────────────────────────────────────────────────────┤
│                   adapters/                          │
│                  (LLM 适配器)                        │
├─────────────────────────────────────────────────────┤
│                  LangChain                          │
│              (基础设施工具链)                        │
├─────────────────────────────────────────────────────┤
│                  LangGraph                           │
│              (图结构编排引擎)                        │
└─────────────────────────────────────────────────────┘
```

---

## 三、核心模块详细结构

### 3.1 harness/ - 操作系统层

```
harness/
├── __init__.py                        # Harness 入口
├── state.py                           # Agent状态定义
├── heartbeat_monitor.py               # 心跳监控
├── integration.py                     # [已实现] HarnessIntegration 统一入口
│
├── interfaces/                         # 接口定义层 [已实现（子集）]
│   ├── __init__.py
│   ├── agent.py                        # IAgent, AgentConfig, AgentResult
│   ├── tool.py                         # ITool, ToolConfig, ToolResult
│   ├── skill.py                        # ISkill, SkillConfig, SkillResult
│   ├── loop.py                         # ILoop, LoopState, LoopResult
│   ├── coordinator.py                  # ICoordinator
│   └── (To-Be)                         # IContext/IRouter/IAdapter 等若需要，应新增实现并补齐接线与测试
│
├── execution/                          # 执行系统 [已实现]
│   ├── __init__.py
│   ├── loop.py                         # 执行循环 (ReAct Loop)
│   ├── retry.py                        # 重试管理器
│   ├── policy.py                       # 执行策略
│   ├── feedback.py                     # [已实现] 反馈机制
│   │
│   ├── langgraph/                      # LangGraph 编排 [已实现]
│   │   ├── __init__.py
│   │   ├── core.py                     # [已实现] 核心功能
│   │   ├── executor.py                 # 图执行器
│   │   ├── callbacks.py                # [已实现] 回调系统
│   │   ├── graphs/                     # 图定义
│   │   │   ├── __init__.py
│   │   │   ├── tri_agent.py           # TriAgent 图
│   │   │   ├── react.py               # ReAct 图
│   │   │   ├── multi_agent.py         # MultiAgent 图
│   │   │   ├── reflection.py          # [已实现] Reflection 图
│   │   │   └── planning.py            # [已实现] Planning 图
│   │   └── nodes/                      # 节点定义
│   │       ├── __init__.py
│   │       ├── registry.py            # 节点注册表
│   │       ├── reason_node.py         # 推理节点
│   │       ├── act_node.py            # 行动节点
│   │       └── observe_node.py        # 观察节点
│   │
│   └── executor/                       # 执行器
│       ├── __init__.py
│       └── unified.py                  # 统一执行器
│
├── coordination/                       # 协调系统 [已实现]
│   ├── __init__.py
│   ├── patterns/                       # 协作模式 (合并实现)
│   │   ├── __init__.py
│   │   └── base.py                     # 所有6种模式合并实现
│   │       # - Pipeline (流水线)
│   │       # - FanOutFanIn (并行处理)
│   │       # - ExpertPool (专家池)
│   │       # - ProducerReviewer (生成审核)
│   │       # - Supervisor (中心调度)
│   │       # - Hierarchical (层级委派)
│   ├── coordinators/                   # 协调器
│   │   └── agent.py                    # Agent协调器
│   └── detector/                       # 检测器
│       └── convergence.py              # 收敛检测
│
├── observability/                      # 观察系统 [已实现]
│   ├── __init__.py
│   ├── monitoring/                     # 监控 (合并实现)
│   │   └── __init__.py                 # MetricCollector, MonitorTarget
│   ├── metrics/                        # 指标 (合并实现)
│   │   └── __init__.py                 # MetricsCollector, TimerContext
│   ├── events/                         # 事件 (合并实现)
│   │   └── __init__.py                 # EventBus, EventRecorder
│   └── alerts/                         # 告警 (合并实现)
│       └── __init__.py                 # AlertManager
│
├── feedback_loops/                     # 反馈循环 [已实现]
│   ├── __init__.py
│   ├── local.py                        # LOCAL 层
│   ├── push.py                         # PUSH 层
│   ├── prod.py                         # PROD 层
│   └── evolution_trigger.py           # 进化触发器
│
├── memory/                             # 记忆系统 [已实现]
│   ├── __init__.py
│   ├── base.py                         # MemoryBase, MemoryEntry
│   ├── short_term.py                   # ShortTermMemory
│   ├── long_term.py                    # LongTermMemory
│   ├── session.py                      # SessionManager
│   └── langchain_adapter.py            # LangChain 适配器
│
├── knowledge/                           # 知识系统 [已实现]
│   ├── __init__.py
│   ├── types.py                        # 知识类型定义
│   ├── retriever.py                    # 知识检索器
│   ├── indexer.py                      # 知识索引器
│   └── evolution.py                    # 知识进化
│
├── infrastructure/                      # 基础设施 [已实现]
│   ├── __init__.py
│   ├── langchain/                      # LangChain 集成
│   │   ├── __init__.py
│   │   ├── models.py                   # 模型集成
│   │   ├── tools.py                    # 工具集成
│   │   └── prompts.py                  # 提示词集成
│   ├── config/                          # 配置
│   │   └── settings.py
│   ├── lifecycle/                       # 生命周期
│   │   └── manager.py
│   ├── hooks/                           # 钩子系统
│   │   └── hook_manager.py
│   ├── approval/                        # [已实现] 审批系统 (Human-in-the-Loop)
│   │   ├── __init__.py
│   │   ├── types.py                    # ApprovalRule, ApprovalRequest, ApprovalResult
│   │   └── manager.py                  # ApprovalManager
│   ├── bootstrap/                       # 启动引导
│   │   └── __init__.py
│   └── di/                              # 依赖注入
│       └── __init__.py
│
└── [规划中]
    ├── permissions/                     # 权限系统 [规划中]
    └── tools/                           # 工具抽象层 [功能在 apps/tools]
```

### 3.2 apps/ - 应用层 [已实现]

```
apps/
├── __init__.py
│
├── agents/                             # Agent 实现
│   ├── __init__.py
│   ├── base.py                         # Agent 基类
│   ├── react.py                        # ReAct Agent
│   ├── plan_execute.py                 # 规划执行 Agent
│   ├── conversational.py               # 对话 Agent
│   ├── multi_agent.py                  # 多 Agent 协作
│   └── rag.py                          # [已实现] RAG Agent
│
├── skills/                             # Skill 实现
│   ├── __init__.py
│   ├── base.py                         # Skill 基类 + 内置技能
│   │   # - TextGeneration
│   │   # - CodeGeneration
│   │   # - DataAnalysis
│   │   # - create_skill()
│   ├── registry.py                     # SkillRegistry（版本管理、启用/禁用、绑定统计）
│   └── executor.py                     # SkillExecutor（执行、超时控制、执行记录）
│
└── tools/                              # Tool 实现
    ├── __init__.py
    ├── base.py                         # Tool 基类 + 内置工具 + ToolRegistry
    │   # - Calculator
    │   # - Search
    │   # - FileOperations
    │   # - ToolRegistry
    │   # - create_tool()
    ├── permission.py                   # PermissionManager（权限管理）
    │   # - Permission (read/write/execute)
    │   # - PermissionEntry
    │   # - PermissionManager
    └── recaller.py                     # TokMem 混合召回系统
        # - TokenRecaller (Token召回)
        # - RAGRecaller (RAG召回)
        # - NeuralEnhancer (神经网络增强)
        # - ToolRecaller (混合召回器)
```

### 3.3 services/ - 核心服务层 [已实现]

```
services/
├── __init__.py                           # 服务入口
├── prompt_service.py                    # PromptService - 提示词模板管理
├── model_service.py                     # ModelService - 模型调用封装（含 FormatAffinity）
├── trace_service.py                     # TraceService - 执行链路追踪（含 DecayType）
├── context_service.py                   # ContextService - 会话上下文管理（含 FileType/ContextFile）
└── file_service.py                      # FileService - Agent 间文件化通信
```

### 3.4 adapters/ - 适配器层 [已实现]

```
adapters/
├── __init__.py
│
└── llm/                                # LLM 适配器
    ├── __init__.py
    ├── base.py                         # 适配器基类 + ILLMAdapter
    ├── openai_adapter.py               # OpenAI + Azure
    ├── anthropic_adapter.py            # Anthropic + Claude
    └── local_adapter.py                # Ollama + vLLM + TGI
```

---

## 四、实现状态说明

### 已实现模块

| 模块 | 状态 | 说明 |
|------|------|------|
| `interfaces/` | ✅ 完成 | 8个核心接口定义 |
| `infrastructure/` | ✅ 完成 | LangChain集成、配置、生命周期、钩子 |
| `execution/` | ✅ 完成 | 循环、重试、策略、LangGraph编排 |
| `coordination/` | ✅ 完成 | 6种协作模式、协调器、收敛检测 |
| `observability/` | ✅ 完成 | 监控、指标、事件、告警 |
| `feedback_loops/` | ✅ 完成 | 三层反馈、进化触发 |
| `memory/` | ✅ 完成 | 短期记忆、长期记忆、会话管理 |
| `knowledge/` | ✅ 完成 | 知识类型、检索、索引 |
| `services/` | ✅ 完成 | 提示词、模型、追踪、上下文、文件通信 |
| `adapters/llm/` | ✅ 完成 | OpenAI、Anthropic、本地模型适配 |
| `apps/agents/` | ✅ 完成 | 5种Agent实现 |
| `apps/skills/` | ✅ 完成 | Skill基类+内置技能+注册表+执行器 |
| `apps/tools/` | ✅ 完成 | Tool基类+内置工具+注册表+权限+召回 |

### 规划中模块

| 模块 | 状态 | 说明 |
|------|------|------|
| `permissions/` | 📋 规划中 | 权限系统 |

---

## 五、LangGraph/LangChain 集成位置

### LangGraph 位置
```
harness/
└── execution/
    └── langgraph/                      # LangGraph 编排
        ├── core.py                     # 核心功能
        ├── executor.py                 # 执行器
        ├── callbacks.py                # 回调系统
        ├── graphs/                      # 图定义
        └── nodes/                       # 节点
```

### LangChain 位置
```
harness/
├── infrastructure/
│   └── langchain/                      # LangChain 集成
│       ├── models.py                   # 模型集成
│       ├── tools.py                    # 工具集成
│       └── prompts.py                  # 提示词集成
└── memory/
    └── langchain_adapter.py            # LangChain 记忆适配
```

---

## 六、依赖关系

```
依赖方向（从上到下）:

┌─────────────┐
│    apps/    │  ← 应用层（具体实现）
└──────┬──────┘
       │ 调用
       ▼
┌─────────────┐
│  harness/   │  ← 操作系统层
│ interfaces/ │     - 定义接口
│ execution/  │     - 执行系统 (含 LangGraph)
│ coordination│     - 协调系统
│ observability│    - 观察系统
│ feedback_loops│   - 反馈循环
│ memory/     │     - 记忆系统
│ knowledge/  │     - 知识系统
│ infra/      │     - 基础设施 (含 LangChain)
└──────┬──────┘
       │ 依赖
       ▼
┌─────────────┐
│  adapters/  │  ← 适配器层
└──────┬──────┘
       │ 调用
       ▼
┌─────────────┐
│ LangChain   │  ← 基础设施工具链
└──────┬──────┘
       │ 构建
       ▼
┌─────────────┐
│ LangGraph   │  ← 图结构编排引擎
└─────────────┘
```

---

## 七、关键设计决策

| 决策项 | 位置 | 理由 |
|--------|------|------|
| LangGraph | `harness/execution/langgraph/` | 编排是执行系统的子能力 |
| LangChain | `harness/infrastructure/langchain/` | 作为基础设施的一部分 |
| 记忆系统 | `harness/memory/` | 作为框架核心能力 |
| 知识系统 | `harness/knowledge/` | 作为框架核心能力 |
| 接口定义 | `harness/interfaces/` | 统一接口规范 |
| 具体实现 | `apps/` | 与框架能力分离 |
| 适配器 | `adapters/` | 外部服务解耦 |
| 协作模式 | `coordination/patterns/base.py` | 合并内聚，减少文件数 |
| 观察模块 | `observability/*/__init__.py` | 合并内聚，简化结构 |

---

*最后更新: 2026-04-14*
