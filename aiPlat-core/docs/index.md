# aiPlat-core 文档索引（设计真值：以代码事实为准）

> ⚠️ 说明：本文档是“导航 + 架构口径摘要”。涉及实现状态时，以 [`ARCHITECTURE_STATUS.md`](./ARCHITECTURE_STATUS.md) 为准，并遵循其可追溯断言规则（代码入口/测试/命令）。

## 核心概念

理解 Harness-Agent-Skill 三者关系是掌握本系统的关键：

### 核心定义

| 概念 | 一句话定义 | 本质 |
|------|-----------|------|
| **Agent** | 能自主完成任务的智能体 | Model + Harness |
| **Harness** | Agent 的运行环境与控制系统 | 模型之外的一切（工具、上下文、约束、反馈） |
| **Skill** | 可复用的能力模块 | 提示词 + 脚本 + 知识的打包 |

### 三者关系

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                     Harness (运行时环境)                 ││
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    ││
│  │  │ 上下文工程   │ │ 架构约束     │ │ 反馈闭环     │    ││
│  │  │ (渐进披露)   │ │ (Hook/沙箱)  │ │ (Ralph Loop) │    ││
│  │  └──────────────┘ └──────────────┘ └──────────────┘    ││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐   ││
│  │  │                  Skill 能力库                     │   ││
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐            │   ││
│  │  │  │code-review│ │doc-gen  │ │web-test │ ...      │   ││
│  │  │  └─────────┘ └─────────┘ └─────────┘            │   ││
│  │  └──────────────────────────────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────┘│
│                              ↓                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                     Model (推理引擎)                     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**核心公式**：
- **Agent = Model + Harness**
- **Skill = 被封装进 Harness 的"能力单元"**

### 关键设计理念

| 理念 | 说明 |
|------|------|
| **Harness 是操作系统** | 管理上下文、执行约束、处理反馈 |
| **Skill 是 App** | 每个 Skill 解决一类特定问题，按需调用，用完即走 |
| **Build to Delete** | 随着模型能力提升，Harness 应逐步"瘦身" |
| **90% 失败不是模型问题** | Agent 的失败通常是 Harness 没搭好 |

> 详细概念说明见 [架构总览](./architecture/index.md)

## Runtime（执行引擎入口）

为避免与 app 层“运行时接入”混淆，core 的 Runtime 入口单独收敛在：

- [Runtime（Core Layer 1）](./runtime/index.md)

---

## 概述

aiPlat-core 是 AI 中台的核心层，负责 AI 能力的核心实现。本层提供智能体编排、技能管理、记忆系统、知识管理等核心 AI 能力，是整个平台的技术核心。

## 架构定位

### 层级关系

aiPlat-core 位于四层架构的第二层（Layer 1），承上启下：

- **向上依赖**：为 aiPlat-platform 提供核心 AI 能力
- **向下依赖**：依赖 aiPlat-infra 提供的基础设施服务
- **被依赖方**：aiPlat-platform、aiPlat-app（通过 platform 间接访问）

### 职责边界

本层负责：

- 智能体生命周期管理与编排
- 技能系统的定义与执行
- 记忆系统的存储与检索
- 知识库的管理与查询
- 工具的注册与调度
- AI 模型的统一封装

本层不负责（To-Be 目标边界，当前仓库未必完全拆分）：

- HTTP 服务与 API 网关（To-Be：由 aiPlat-platform 提供；As-Is：当前仓库的 API 入口主要在 `core/server.py`）
- 用户认证与平台级租户管理（To-Be：由 aiPlat-platform 提供；As-Is：core 内已具备权限/审批等最小治理能力）
- 租户隔离与资源配额（由 aiPlat-platform 提供）
- 前端界面与用户交互（由 aiPlat-app 提供）
- 数据库连接池与缓存（由 aiPlat-infra 提供）

## 核心模块

### 框架基础

aiPlat-core 基于 LangGraph 和 LangChain 构建，提供 AI 能力的技术底座。

**LangGraph 集成**：

LangGraph 提供基于图结构的智能体编排能力，支持复杂工作流的定义和执行。

| 特性 | 说明 |
|------|------|
| 节点（Node） | 代表一个执行步骤，可以是 Agent、Tool、Condition 等 |
| 边（Edge） | 定义节点之间的执行顺序和条件跳转 |
| 状态（State） | 在节点间传递的上下文数据 |
| 循环（Cycle） | 支持迭代执行，用于多轮对话和递归任务 |

**LangChain 集成**：

LangChain 提供大语言模型调用的标准化接口和工具链。

| 组件 | 说明 |
|------|------|
| LCEL | LangChain Expression Language，链式调用表达式 |
| Chat Models | 聊天模型接口，支持 OpenAI/Anthropic/本地模型 |
| Memory | 记忆组件，支持短期/长期记忆 |
| Tools | 工具接口，标准化工具定义和调用 |
| Agents | Agent 接口，定义智能体的行为模式 |

**框架与核心模块的关系**：

```
LangGraph (图结构编排)
    ↓
LangChain (基础设施工具链)
    ↓
Harness (操作系统层)
    ├── interfaces/    (接口定义) ✅ 已实现
    ├── execution/    (执行系统，含 LangGraph) ✅ 已实现
    ├── coordination/ (协调系统) ✅ 已实现
    ├── observability/(观察系统) ✅ 已实现
    ├── feedback_loops/(反馈循环) ✅ 已实现
    ├── infrastructure/(基础设施，含 LangChain) ✅ 已实现
    ├── memory/       (记忆系统) ✅ 已实现
    └── knowledge/    (知识系统) ✅ 已实现
    ↓
Apps (应用层)
    ├── agents/       (Agent 实现) ✅ 已实现
    ├── skills/       (Skill 实现) ✅ 已实现
    └── tools/        (Tool 实现) ✅ 已实现
    ↓
Adapters (适配器层)
    └── llm/          (LLM 适配器) ✅ 已实现
    ↓
Management (管理层) ✅ 已实现
    ├── agent_manager.py    (Agent 管理)
    ├── skill_manager.py    (Skill 管理)
    ├── memory_manager.py   (Memory 管理)
    ├── knowledge_manager.py(Knowledge 管理)
    ├── adapter_manager.py  (Adapter 管理)
    └── harness_manager.py  (Harness 管理)
    ↓
Services (服务层) ✅ 已实现
    ├── prompt_service.py   (提示词管理)
    ├── model_service.py    (模型调用封装)
    ├── trace_service.py    (追踪服务)
    └── context_service.py  (上下文管理)

规划中的模块（To-Be）：
    └── platform-level permissions/tenant/quota（平台控制面）

---

## 证据索引（Evidence Index｜抽样）

- API 入口与生命周期初始化：`core/server.py`
- 现状真值与修复决策：`docs/ARCHITECTURE_STATUS.md`
```

**相关文档**：[框架基础文档](./framework/index.md) - 包含 LangChain/LangGraph/Harness 详细关系及[项目结构](./framework/structure.md)，[架构总览](./architecture/index.md) - 完整层次关系图

### harness - 智能体框架

智能体框架是核心层的基础设施，提供智能体的定义、创建、运行和管理能力。

**核心概念**：

- **Agent**：智能体是具有自主决策能力的执行单元，能够理解用户意图、规划执行步骤、调用工具完成任务
- **AgentContext**：智能体执行上下文，包含当前会话状态、历史记录、环境变量等信息
- **AgentState**：智能体状态机，管理智能体的生命周期状态转换

**主要能力**：

- 智能体定义与配置
- 智能体实例化与运行
- 状态管理与生命周期控制
- 错误处理与重试机制
- 执行日志与追踪

**设计原则**：

- 智能体应该是无状态的，状态通过上下文传递
- 智能体应该支持异步执行
- 智能体应该支持中断与恢复
- 智能体应该支持并行执行多个任务

**相关文档**：[harness 模块文档](./harness/index.md)

#### harness 详细子系统

| 子系统 | 说明 | 文档 |
|--------|------|------|
| **执行系统** | Agent 循环、重试、Hook 拦截 | [执行系统](./harness/execution.md) |
| **协调系统** | 多 Agent 协作、6 种模式 | [协调系统](./harness/coordination.md) |
| **观察系统** | 监控、告警、观测驱动控制 | [观察系统](./harness/observability.md) |
| **反馈循环** | LOCAL/PUSH/PROD 三层反馈 | [反馈循环](./harness/feedback-loops.md) |
| **反馈门禁** | 可插拔质量验证器 | [反馈门禁](./harness/feedback-gates.md) |
| **渐进式披露** | 按需加载上下文机制 | [渐进式披露](./harness/progressive-disclosure.md) |

### tools - 工具系统

工具系统负责管理 Agent 可调用的外部工具，提供工具注册、发现、调用和统计能力。

| 工具类型 | 文档 |
|---------|------|
| **基础工具** | [工具系统](./tools/index.md) |
| **增强工具** | [工具增强](./tools/enhancement.md) |

### mcp - MCP 协议集成

MCP (Model Context Protocol) 是 AI Agent 与外部工具/服务交互的标准协议。

| 功能 | 文档 |
|------|------|
| **MCP 集成** | [MCP 协议](./mcp/index.md) |

### orchestration - 编排引擎

编排引擎负责协调多个智能体、技能、工具的协同工作，实现复杂任务的自动化执行。

**核心概念**：

- **Workflow**：工作流，定义任务执行的步骤和条件
- **Step**：工作流步骤，可以是智能体调用、技能执行、工具调用等
- **Condition**：条件分支，根据执行结果决定下一步骤
- **Loop**：循环结构，支持迭代执行
- **Parallel**：并行结构，支持同时执行多个步骤

**主要能力**：

- 工作流定义与解析
- 工作流执行引擎
- 条件分支与循环控制
- 并行执行与结果合并
- 错误处理与补偿机制
- 执行状态追踪

**设计原则**：

- 工作流定义应该是声明式的，易于理解和维护
- 工作流执行应该是可观测的，支持实时监控
- 工作流应该支持版本管理
- 工作流应该支持热更新

**执行计划类型**：

编排引擎根据任务复杂度自动选择合适的执行计划：

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| QuickPlan | 快速执行，无复杂规划 | 简单任务 |
| ParallelPlan | 并行执行多个子任务 | 独立子任务 |
| ReasoningPlan | 深度推理，逐步求解 | 复杂问题 |
| HybridPlan | 多资源协作，混合策略 | 综合任务 |
| ConservativePlan | 保守执行，优先稳定性 | 关键任务 |

### 自我进化与反馈循环

> 详见 [Agent 自我进化能力](./agents/index.md#自我进化能力) 和 [Harness 三层反馈循环](./harness/index.md#6-三层反馈循环系统)

Agent 支持基于执行历史的参数自动优化（LOCAL → PUSH → PROD 三层进化），确保优化策略的安全性和可回滚性。

**关键机制**：

| 机制 | 说明 |
|------|------|
| **Format Affinity** | 模型对特定输出格式有偏好，高格式亲和性意味着更好的执行效果 |
| **Value Decay Curve** | 不同类型的反馈价值衰减速度不同，需要区别对待 |
| **Build to Delete** | 随着模型能力提升，Harness 应逐步简化，减少不必要的约束 |

**相关文档**：[harness 模块文档](./harness/index.md)

### agents - 智能体实现

智能体实现模块提供各类预定义智能体的具体实现，是智能体框架的具体应用。

**智能体类型**：

- **ReAct Agent**：推理-行动智能体，通过推理决定下一步行动
- **Plan-and-Execute Agent**：规划-执行智能体，先规划后执行
- **Conversational Agent**：对话智能体，专注于多轮对话
- **Tool-Using Agent**：工具使用智能体，擅长调用外部工具
- **RAG Agent**：检索增强生成智能体，结合知识库回答问题
- **Multi-Agent**：多智能体协作，多个智能体协同完成任务

**主要能力**：

- 各类智能体的具体实现
- 智能体配置与参数调优
- 智能体性能优化
- 智能体测试与评估

**设计原则**：

- 每个智能体应该有明确的职责边界
- 智能体之间应该通过消息通信
- 智能体应该支持插件化扩展
- 智能体应该支持自定义配置

**自我进化与反馈循环**：

> 详见 [Agent 自我进化能力](./agents/index.md#自我进化能力) 和 [Harness 三层反馈循环](./harness/index.md#6-三层反馈循环系统)

Agent 支持基于执行历史的参数自动优化（LOCAL → PUSH → PROD 三层进化），确保优化策略的安全性和可回滚性。

**相关文档**：[agents 模块文档](./agents/index.md)、[harness 模块文档](./harness/index.md)

### skills - 技能系统

技能系统定义和管理智能体可执行的能力单元，是智能体完成任务的具体手段。

**核心概念**：

- **Skill**：技能，是智能体可执行的能力单元，如文本生成、代码解释、数据分析等
- **SkillRegistry**：技能注册表，管理所有可用技能
- **SkillExecutor**：技能执行器，负责技能的具体执行
- **SkillContext**：技能执行上下文，包含输入参数、环境信息等

**技能类型**：

- **生成类技能**：文本生成、代码生成、图像生成等
- **分析类技能**：文本分析、代码分析、数据分析等
- **转换类技能**：格式转换、语言翻译、代码重构等
- **检索类技能**：知识检索、文档搜索、信息抽取等
- **执行类技能**：命令执行、API 调用、工作流触发等

**主要能力**：

- 技能定义与注册
- 技能发现与匹配
- 技能执行与监控
- 技能版本管理
- 技能权限控制

**Skill 结构（Agent Skill 模式）**：

```
my-skill/
├── SKILL.md         # 元数据 + 核心指令
├── handler.py        # Skill 实现
├── scripts/          # 确定性脚本（可选）
└── references/       # 按需加载知识（可选）
```

**设计原则**：

- 技能应该是无副作用的纯函数（除非明确标记）
- 技能应该有清晰的输入输出定义
- 技能应该支持幂等执行
- 技能应该支持超时控制

**Skill Factory 标准化开发流程**：

Skill Factory 提供完整的 AI Skill 标准化开发流程：

1. **需求分析**：根据需求定义技能规格
2. **模板生成**：自动生成 skill.yaml 和 SKILL.md
3. **原型实现**：基于原型类型填充代码
4. **质量检查**：自动化校验和测试

**相关文档**：[Skill 架构设计](./skills/architecture.md)、[harness 模块文档](./harness/index.md)

### memory - 记忆系统

记忆系统负责智能体的短期记忆和长期记忆管理，支持上下文保持和经验积累。

**核心概念**：

- **Memory**：记忆，是智能体在执行过程中积累的信息
- **ShortTermMemory**：短期记忆，存储当前会话的上下文信息
- **LongTermMemory**：长期记忆，存储跨会话的经验和知识
- **MemoryStore**：记忆存储，负责记忆的持久化
- **MemoryRetriever**：记忆检索，负责从记忆中检索相关信息

**记忆类型**：

- **对话记忆**：存储对话历史，支持多轮对话
- **执行记忆**：存储执行历史，支持任务恢复
- **经验记忆**：存储成功/失败案例，支持学习
- **知识记忆**：存储外部知识，支持知识增强

**主要能力**：

- 记忆存储与检索
- 记忆压缩与摘要
- 记忆遗忘与清理
- 记忆迁移与同步
- 记忆分析与统计

**设计原则**：

- 短期记忆应该快速访问，长期记忆应该持久可靠
- 记忆应该支持按相关性检索
- 记忆应该支持自动过期清理
- 记忆应该支持跨会话共享

**相关文档**：[harness 模块文档](./harness/index.md)

### knowledge - 知识管理

知识管理模块负责知识库的构建、维护和查询，支持检索增强生成（RAG）等场景。

**核心概念**：

- **KnowledgeBase**：知识库，是结构化知识的集合
- **Document**：文档，是知识的基本单元
- **Chunk**：文档片段，是检索的基本单元
- **Embedding**：向量嵌入，是语义表示
- **Index**：索引，支持快速检索

**知识类型**：

- **文档知识**：PDF、Word、Markdown 等文档
- **结构化知识**：数据库、表格、知识图谱
- **代码知识**：代码库、API 文档
- **网页知识**：网页内容、在线文档

**主要能力**：

- 文档解析与分块
- 向量嵌入与索引
- 语义检索与排序
- 知识图谱构建
- 知识更新与同步

**设计原则**：

- 知识应该支持增量更新
- 检索应该支持混合检索（向量+关键词）
- 知识应该支持多模态（文本、图像、代码）
- 知识应该支持权限控制

**相关文档**：[harness 模块文档](./harness/index.md)

### tools - 工具系统

工具系统负责外部工具的注册、管理和调用，扩展智能体的能力边界。

**核心概念**：

- **Tool**：工具，是智能体可调用的外部能力
- **ToolRegistry**：工具注册表，管理所有可用工具
- **ToolExecutor**：工具执行器，负责工具的具体调用
- **ToolSchema**：工具模式，定义工具的输入输出格式

**工具类型**：

- **计算工具**：数学计算、代码执行、数据处理
- **检索工具**：搜索引擎、数据库查询、API 调用
- **生成工具**：图像生成、代码生成、文档生成
- **操作工具**：文件操作、系统命令、外部服务调用

**主要能力**：

- 工具定义与注册
- 工具发现与匹配
- 工具调用与执行
- 工具权限控制
- 工具调用监控

**设计原则**：

- 工具应该有清晰的输入输出定义
- 工具应该支持超时控制
- 工具应该支持权限校验
- 工具调用应该有完整的日志记录

**Hand System 专用工具封装**：

提供 20+ 专用工具封装（Hand），每个 Hand 针对特定场景优化：

- **FileHand**：文件操作（读写、搜索、压缩）
- **APIHand**：API 调用封装（REST、GraphQL）
- **CodeHand**：代码执行与解释
- **DatabaseHand**：数据库操作（SQL、NoSQL）
- **BrowserHand**：浏览器自动化
- **TerminalHand**：终端命令执行

每个 Hand 提供：
- 标准化接口
- 错误处理封装
- 资源管理
- 调用追踪

**相关文档**：[harness 模块文档](./harness/index.md)

### services - 核心服务 ✅ 已实现

> **状态**: ✅ 已实现（v1.0）
> **文档**: [services 模块文档](./services/index.md)

核心服务模块提供公共的基础服务能力，供其他模块调用。

**已实现的服务**：

- **PromptService**：提示词管理，包括模板管理、变量替换、版本控制
- **ModelService**：模型调用封装，提供统一的模型访问接口
- **TraceService**：追踪服务，记录执行链路和性能指标
- **ContextService**：上下文管理，管理会话上下文和状态

**边界定义**：

**包含**：
- 提示词模板管理和渲染
- 模型调用的统一封装
- 执行过程的追踪记录
- 会话上下文的管理

**不包含**：
- 业务逻辑（放 agents/skills）
- 数据存储（放 memory/knowledge）
- 工具实现（放 tools）
- 工作流定义（放 orchestration）

**相关文档**：[services 模块文档](./services/index.md)

### models - 模型封装

模型封装模块提供大语言模型的统一访问能力。

**模型类型**：

- **OpenAI**：GPT 系列模型
- **Anthropic**：Claude 系列模型
- **本地模型**：支持 Ollama、vLLM 等本地部署

**主要能力**：

- 模型调用接口统一
- 配置热更新
- 调用重试和降级
- 成本追踪

**相关文档**：[harness 模块文档](./harness/index.md)

## 设计原则

### 依赖原则

- **单向依赖**：只依赖 aiPlat-infra，不依赖 aiPlat-platform 和 aiPlat-app
- **接口隔离**：通过接口与基础设施交互，不直接依赖具体实现
- **依赖注入**：使用依赖注入管理依赖关系，支持测试和替换

### 设计原则

- **单一职责**：每个模块只负责一个核心能力
- **开放封闭**：对扩展开放，对修改封闭
- **依赖倒置**：依赖抽象，不依赖具体实现
- **接口隔离**：接口要小而专，不要大而全
- **最小知识**：模块之间应该最小化相互了解

### 编码规范（移至开发者指南）

> 编码规范相关内容请参考 [开发者指南](./by-role/developer/index.md)

### 模块间依赖规则

各模块之间的依赖关系应遵循以下规则：

| 模块 | 可依赖 | 禁止依赖 |
|------|--------|----------|
| harness | 无（基础层） | - |
| orchestration | harness, agents, skills, tools | memory, knowledge |
| agents | harness, memory, knowledge, tools, models, services | - |
| skills | harness, tools, models, services | memory, knowledge |
| memory | services | agents, skills, tools |
| knowledge | services, models | agents, skills |
| tools | services | agents, skills |
| services | aiPlat-infra | - |
| models | aiPlat-infra | agents, skills |

**依赖规则说明**：

- **自下而上**：模块只能依赖比自己更基础的模块
- **禁止循环**：模块之间不能形成循环依赖
- **接口隔离**：通过接口通信，不直接依赖具体实现

### 模块依赖矩阵

| 模块 | harness | orchestration | agents | skills | memory | knowledge | tools | services | models |
|------|:-------:|:-------------:|:------:|:------:|:------:|:---------:|:-----:|:--------:|:------:|
| harness | - | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| orchestration | ✓ | - | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ |
| agents | ✓ | ✗ | - | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| skills | ✓ | ✗ | ✗ | - | ✗ | ✗ | ✓ | ✓ | ✓ |
| memory | ✗ | ✗ | ✗ | ✗ | - | ✗ | ✗ | ✓ | ✗ |
| knowledge | ✗ | ✗ | ✗ | ✗ | ✗ | - | ✗ | ✓ | ✓ |
| tools | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | - | ✓ | ✗ |
| services | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | - | ✗ |
| models | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | - |

✓ = 允许依赖 | ✗ = 禁止依赖

### 与 infra 层边界

**core 层从 infra 获取什么**：

- **计算资源抽象**：通过工厂接口获取，不关心具体实现（K8s/Docker/裸机）
- **数据存储抽象**：通过数据访问接口获取，不关心 SQL/NoSQL/文件
- **模型服务抽象**：通过模型客户端获取，不关心 OpenAI/Anthropic/本地模型

**core 层不关心什么**：

- **资源调度细节**：如何分配 CPU/GPU/内存
- **数据持久化策略**：备份、恢复、副本机制
- **服务发现机制**：域名解析、负载均衡
- **认证授权实现**：Token 验证、权限模型

**边界原则**：

- core 只使用 infra 提供的抽象接口
- infra 的具体实现对 core 透明
- 切换 infra 实现（如换数据库）不影响 core

### 门面模式原理（CoreFacade）

**为什么需要 CoreFacade**：

aiPlat-core 包含 7 个模块（harness、orchestration、agents、skills、memory、knowledge、tools），如果直接暴露给上层 platform，会导致：

1. **耦合紧密**：platform 直接依赖具体模块，core 重构影响 platform
2. **边界模糊**：难以区分哪些是 core 职责，哪些是 platform 职责
3. **升级困难**：模块 API 变化需要同步修改 platform

**CoreFacade 解决什么问题**：

- **统一入口**：platform 只需依赖 CoreFacade，无需了解内部模块
- **隔离变化**：core 内部重构不影响 platform 调用
- **版本演进**：facade 接口可以独立版本控制

**CoreFacade 不做什么**：

- 不暴露内部模块的具体类
- 不允许 platform 直接访问 infra
- 不处理业务逻辑（由 core 模块处理）

### 执行计划自动选择原理

编排引擎根据任务特征自动选择最优执行计划：

| 选择依据 | QuickPlan | ParallelPlan | ReasoningPlan | HybridPlan | ConservativePlan |
|---------|-----------|--------------|---------------|------------|------------------|
| 任务复杂度 | 简单 | 中等 | 复杂 | 综合 | 关键 |
| 子任务独立性 | - | 独立 | 依赖 | 混合 | - |
| 推理需求 | 低 | 低 | 高 | 中等 | 中等 |
| 执行耗时预期 | < 1s | < 5s | < 30s | < 60s | < 10s |

**自动选择流程**：

1. **复杂度评估**：分析任务描述的关键词、步骤数、依赖关系
2. **历史参考**：查询相似任务的执行计划及效果
3. **资源评估**：当前系统负载、可用并发度
4. **兜底策略**：无法判断时默认使用 QuickPlan

### 自我进化触发机制

> 详细说明见 [Harness 自我进化机制](./harness/index.md#5-自我进化机制) 和 [三层反馈循环](./harness/index.md#6-三层反馈循环系统)

Agent 通过三层机制实现自我进化：性能追踪 → 阈值触发 → 分层进化（LOCAL → PUSH → PROD），每层独立存储、独立回滚，确保优化策略的安全性。

## 按角色文档

- [架构师指南](./by-role/architect/index.md) - 架构设计、技术选型、模块划分
- [开发者指南](./by-role/developer/index.md) - 开发规范、API 使用、最佳实践
- [运维指南](./by-role/ops/index.md) - 部署配置、监控告警、故障排查
- [用户指南](./by-role/user/index.md) - 功能使用、配置说明、常见问题

### 各角色文档内容说明

| 角色 | 文档目录 | 包含内容 |
|------|----------|----------|
| 架构师 | `by-role/architect/` | 整体架构设计、模块依赖关系、核心抽象定义、技术选型依据、设计原则、扩展机制 |
| 开发者 | `by-role/developer/` | 开发环境搭建、核心模块使用、模块开发流程、最佳实践、测试指南、调试技巧 |
| 运维 | `by-role/ops/` | 部署配置说明、监控指标、告警规则、故障排查、备份恢复、安全管理 |
| 用户 | `by-role/user/` | 核心概念、使用指南、最佳实践、常见问题 |

## 相关链接

- [主文档索引](../../docs/index.md) - 返回主文档
- [基础设施层文档](../aiPlat-infra/docs/index.md) - aiPlat-infra 文档
- [平台服务层文档](../aiPlat-platform/docs/index.md) - aiPlat-platform 文档
- [应用层文档](../aiPlat-app/docs/index.md) - aiPlat-app 文档

---

*最后更新: 2026-04-14*
