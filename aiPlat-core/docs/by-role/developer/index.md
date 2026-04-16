# 👨‍💻 核心层开发者指南（As-Is 对齐 + To-Be 示例）

> 说明：本文档包含部分 To-Be 的工程化命令/配置示例（make/config/init_registry 等）。涉及实现状态，以代码事实为准，并遵循 [`ARCHITECTURE_STATUS.md`](../../ARCHITECTURE_STATUS.md) 的可追溯规则。

> aiPlat-core - 开发指南与最佳实践

---

## 🎯 开发者关注点

作为核心层开发者，您需要了解：
- **如何使用**：如何调用 Agent、Skill、编排引擎等核心能力
- **如何扩展**：如何添加新的 Agent、Skill、工具实现
- **如何测试**：如何编写单元测试和集成测试
- **最佳实践**：开发中的最佳实践

---

## 🛠️ 开发环境搭建

### 前置条件

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Python | 3.10+ | 后端开发 |
| Poetry | 1.7+ | 依赖管理 |
| Make | 3.81+ | 构建脚本 |

### 安装依赖

```bash
cd aiPlat-core
poetry install
```

### 配置环境

```bash
# 复制配置模板
cp config/core/agents.yaml.example config/core/agents.yaml
cp config/core/skills.yaml.example config/core/skills.yaml

# 编辑配置文件
vi config/core/agents.yaml
```

### 验证环境

```bash
# 运行单元测试
make test-core-unit

# 检查类型
make typecheck-core
```

---

## 🚀 快速开始

### 5 分钟跑起来

**步骤一：初始化注册表（To-Be 示例）**
```bash
# To-Be：独立 init_registry 命令
# As-Is：启动 `core/server.py` 时会在 lifespan 中执行 agents/skills discovery 并 seed 默认权限
```

**步骤二：注册 Agent（To-Be 示例）**
```bash
# 注册内置 Agent
# To-Be：显式注册命令
```

**步骤三：测试 Agent**
```bash
# 运行 Agent 测试
make test-agent-basic
```

---

## 📖 核心模块使用

### harness - 智能体框架

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取 Agent 注册表 | 调用 `get_agent_registry()` | `core/apps/agents/base.py` |
| 注册 Agent | 调用 `registry.register(name, agent)` | `core/apps/agents/base.py` |
| 获取 Agent | 调用 `registry.get(name)` | `core/apps/agents/base.py` |
| 执行 Agent | 调用 `agent.execute(context)` | `core/apps/agents/base.py` |
| 创建上下文 | 构造 `AgentContext(session_id, user_id, messages, variables, ...)` | `core/harness/interfaces/agent.py` |

**如何添加新的 Agent 类型**：

1. **创建 Agent 文件**：在 `core/apps/agents/` 下创建 `my_agent.py`
2. **继承基类**：继承 `BaseAgent` 类，实现 `execute()` 方法
3. **注册 Agent**：在应用启动时调用 `registry.register("my_agent", MyAgent(config))`
4. **添加配置**：在 `config/core/agents.yaml` 中添加 Agent 配置
5. **编写测试**：在 `tests/unit/core/apps/agents/` 下添加测试文件

**相关文件位置**：
- Agent 基类：`core/apps/agents/base.py`
- ReAct Agent：`core/apps/agents/react.py`
- 规划执行 Agent：`core/apps/agents/plan_execute.py`
- 对话 Agent：`core/apps/agents/conversational.py`
- RAG Agent：`core/apps/agents/rag.py`
- 多 Agent 协作：`core/apps/agents/multi_agent.py`
- Agent 接口定义：`core/harness/interfaces/agent.py`
- 上下文数据结构：`core/harness/interfaces/agent.py: AgentContext`
- LangGraph 图定义：`core/harness/execution/langgraph/graphs/`

---

### orchestration - 编排引擎

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建协调器 | 调用 `AgentCoordinator(config)` | `core/harness/coordination/coordinators/agent.py` |
| 执行多Agent协作 | 调用 `coordinator.execute(agents, task)` | `core/harness/coordination/coordinators/agent.py` |
| 添加收敛检测 | 调用 `ConvergenceDetector()` | `core/harness/coordination/detector/convergence.py` |
| 配置协作模式 | 调用协调模式（Pipeline/Fan-out等） | `core/harness/coordination/patterns/` |
| 执行LangGraph图 | 创建 Graph 并执行 | `core/harness/execution/langgraph/graphs/` |

**协作模式**：
- **Pipeline**：流水线模式，顺序处理
- **Fan-out/Fan-in**：并行处理，结果汇总
- **Expert Pool**：动态选择最合适的 Agent
- **Producer-Reviewer**：生成+审核，二次验证
- **Supervisor**：中心化调度
- **Hierarchical**：层级任务拆解

**相关文件位置**：
- 协调器：`core/harness/coordination/coordinators/agent.py`
- 收敛检测：`core/harness/coordination/detector/convergence.py`
- 协作模式基类：`core/harness/coordination/patterns/base.py`
- LangGraph 图：`core/harness/execution/langgraph/graphs/`
- 执行器：`core/harness/execution/executor/unified.py`

---

### agents - 智能体实现

**详细文档**：[harness 模块文档](../../harness/index.md)

**内置 Agent 类型**：

| Agent 类型 | 适用场景 | 参考文件 |
|-----------|----------|----------|
| ReActAgent | 需要推理决策的任务 | `core/apps/agents/react.py` |
| PlanExecuteAgent | 需要规划执行的复杂任务 | `core/apps/agents/plan_execute.py` |
| ConversationalAgent | 多轮对话场景 | `core/apps/agents/conversational.py` |
| RAGAgent | 知识库问答场景 | `core/apps/agents/rag.py` |
| MultiAgent | 多角色协作场景 | `core/apps/agents/multi_agent.py` |
| ReflectionAgent | 自我审视+修正 | `core/harness/execution/langgraph/graphs/reflection.py` |
| PlanningAgent | 任务分解+执行 | `core/harness/execution/langgraph/graphs/planning.py` |
| TriAgent | Planner-Generator-Evaluator | `core/harness/execution/langgraph/graphs/tri_agent.py` |

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 使用 ReActAgent | `agent = ReActAgent(config)` | `core/apps/agents/react.py` |
| 使用 PlanExecuteAgent | `agent = PlanExecuteAgent(config)` | `core/apps/agents/plan_execute.py` |
| 使用 ConversationalAgent | `agent = ConversationalAgent(config)` | `core/apps/agents/conversational.py` |

---

### skills - 技能系统

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取 Skill 注册表 | 调用 `get_skill_registry()` | `core/apps/skills/registry.py` |
| 注册 Skill | 调用 `registry.register(skill)` | `core/apps/skills/registry.py` |
| 获取 Skill | 调用 `registry.get(name)` | `core/apps/skills/registry.py` |
| 执行 Skill | 调用 `executor.execute(name, params)` | `core/apps/skills/executor.py` |
| 获取 Skill 版本 | 调用 `registry.get_versions(name)` | `core/apps/skills/registry.py` |
| 启用/禁用 Skill | 调用 `registry.enable(name)` / `registry.disable(name)` | `core/apps/skills/registry.py` |

**如何添加新的 Skill**：

1. **创建 Skill 文件**：在 `core/apps/skills/` 下创建 `my_skill.py`
2. **继承基类**：继承 `BaseSkill` 类，实现 `execute()` 方法
3. **定义输入输出**：定义 Skill 的输入参数和输出格式
4. **注册 Skill**：在应用启动时调用 `registry.register("my_skill", MySkill())`
5. **编写测试**：在 `tests/unit/core/apps/skills/` 下添加测试文件

**相关文件位置**：
- Skill 基类：`core/apps/skills/base.py`
- Skill 注册表：`core/apps/skills/registry.py`
- Skill 执行器：`core/apps/skills/executor.py`
- Skill 接口定义：`core/harness/interfaces/skill.py`

---

### memory - 记忆系统

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建短期记忆 | 调用 `ShortTermMemory(config)` | `core/harness/memory/short_term.py` |
| 创建长期记忆 | 调用 `LongTermMemory(config)` | `core/harness/memory/long_term.py` |
| 存储记忆 | 调用 `memory.store(key, value)` | `core/harness/memory/base.py` |
| 检索记忆 | 调用 `memory.retrieve(query)` | `core/harness/memory/base.py` |
| 清理记忆 | 调用 `memory.clear_expired()` | `core/harness/memory/base.py` |

**记忆类型**：

| 记忆类型 | 用途 | 参考文件 |
|---------|------|----------|
| ShortTermMemory | 当前会话信息 | `core/harness/memory/short_term.py` |
| LongTermMemory | 跨会话经验 | `core/harness/memory/long_term.py` |
| SessionMemory | 会话状态管理 | `core/harness/memory/session.py` |

**相关文件位置**：
- 记忆基类：`core/harness/memory/base.py`
- 短期记忆：`core/harness/memory/short_term.py`
- 长期记忆：`core/harness/memory/long_term.py`
- LangChain 适配器：`core/harness/memory/langchain_adapter.py`

---

### knowledge - 知识管理

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建知识库 | 调用 `KnowledgeIndexer(config)` | `core/harness/knowledge/indexer.py` |
| 添加文档 | 调用 `indexer.index(doc)` | `core/harness/knowledge/indexer.py` |
| 检索知识 | 调用 `retriever.retrieve(query, top_k)` | `core/harness/knowledge/retriever.py` |
| 知识进化 | 调用 `evolution.evolve()` | `core/harness/knowledge/evolution.py` |

**文档处理流程**：
1. 解析文档（PDF、Word、Markdown 等）
2. 分块处理
3. 向量嵌入
4. 存储索引

**相关文件位置**：
- 知识索引器：`core/harness/knowledge/indexer.py`
- 知识检索器：`core/harness/knowledge/retriever.py`
- 知识进化：`core/harness/knowledge/evolution.py`
- 知识类型定义：`core/harness/knowledge/types.py`

---

### tools - 工具系统

**详细文档**：[tools 模块文档](../../tools/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取工具注册表 | 调用 `get_tool_registry()` | `core/apps/tools/base.py` |
| 注册工具 | 调用 `registry.register(name, tool)` | `core/apps/tools/base.py` |
| 获取工具 | 调用 `registry.get(name)` | `core/apps/tools/base.py` |
| 执行工具 | 调用 `tool.execute(params)` | `core/apps/tools/base.py` |

**如何添加新的工具**：

1. **创建工具文件**：在 `core/apps/tools/` 下创建 `my_tool.py`
2. **继承基类**：继承 `BaseTool` 类，实现 `execute()` 方法
3. **定义 Schema**：定义工具的输入输出 Schema
4. **注册工具**：在应用启动时调用 `registry.register("my_tool", MyTool())`
5. **编写测试**：在 `tests/unit/core/apps/tools/` 下添加测试文件

**相关文件位置**：
- 工具基类 + 注册表：`core/apps/tools/base.py`
- 内置工具：CalculatorTool, SearchTool, FileOperationsTool（均位于 `base.py` 内）
- 工具接口定义：`core/harness/interfaces/tool.py`

---

### services - 核心服务

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取提示词服务 | 调用 `PromptService(config)` | `core/services/prompt_service.py` |
| 获取模型服务 | 调用 `ModelService(config)` | `core/services/model_service.py` |
| 获取上下文服务 | 调用 `ContextService()` | `core/services/context_service.py` |
| 获取追踪服务 | 调用 `TraceService(config)` | `core/services/trace_service.py` |
| 获取文件服务 | 调用 `FileService()` | `core/services/file_service.py` |

**相关文件位置**：
- 提示词服务：`core/services/prompt_service.py`
- 模型服务：`core/services/model_service.py`
- 上下文服务：`core/services/context_service.py`
- 追踪服务：`core/services/trace_service.py`
- 文件服务：`core/services/file_service.py`

---

### models - 模型封装

**详细文档**：[harness 模块文档](../../harness/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取 OpenAI 提供商 | 调用 `OpenAIProvider(config)` | `core/models/openai.py` |
| 获取 Anthropic 提供商 | 调用 `AnthropicProvider(config)` | `core/models/anthropic.py` |
| 获取本地模型提供商 | 调用 `LocalProvider(config)` | `core/models/local.py` |

**相关文件位置**：
- 模型提供商基类：`core/models/base.py`
- OpenAI 提供商：`core/models/openai.py`
- Anthropic 提供商：`core/models/anthropic.py`

---

## 🔧 如何扩展

### 添加新的 Agent

**步骤**：

1. **创建 Agent 文件**：在 `core/apps/agents/` 下创建新的Agent 实现
2. **继承基类**：继承 `BaseAgent` 类
3. **实现方法**：实现 `execute()` 等必要方法
4. **添加配置**：在 `config/core/agents.yaml` 中添加配置
5. **注册 Agent**：在应用启动时注册
6. **编写测试**：添加单元测试和集成测试

**Agent 实现模板**：
- 必须实现 `execute(context: AgentContext)` 方法
- 必须处理异常情况
- 必须支持异步执行
- 必须返回执行结果

### 添加新的 Skill

**步骤**：

1. **创建 Skill 文件**：在 `core/apps/skills/` 下创建新的 Skill 实现
2. **继承基类**：继承 `BaseSkill` 类
3. **定义输入输出**：定义 Skill 的输入参数和输出格式
4. **实现方法**：实现 `execute(context: SkillContext)` 方法
5. **注册 Skill**：在应用启动时注册
6. **编写测试**：添加单元测试

**Skill 实现模板**：
- 必须定义清晰的输入输出
- 必须是无副作用的纯函数（除非明确标记）
- 必须支持幂等执行
- 必须支持超时控制

### 添加新的工具

**步骤**：

1. **创建工具文件**：在 `core/apps/tools/` 下创建新的工具实现
2. **继承基类**：继承 `BaseTool` 类
3. **定义 Schema**：定义工具的输入输出 Schema
4. **实现方法**：实现 `execute(params)` 方法
5. **注册工具**：在应用启动时注册
6. **编写测试**：添加单元测试

---

## 🧪 测试

### 测试目录结构

```
tests/
├── unit/                       # 单元测试
│   ├── core/
│   │   ├── apps/
│   │   │   ├── agents/
│   │   │   │   └── test_agents.py
│   │   │   ├── skills/
│   │   │   │   └── test_skills.py
│   │   │   └── tools/
│   │   │       └── test_tools.py
│   │   └── harness/
│   │       ├── test_graphs/
│   │       │   ├── test_reflection.py
│   │       │   └── test_planning.py
│   │       └── test_approval/
│   │           └── test_approval.py
│   └── integration/            # 集成测试
│       ├── test_agent_execution.py
│       └── test_workflow_execution.py
└── fixtures/                   # 测试数据
    └── core/
        ├── sample_agents.yaml
        └── sample_skills.yaml
```

### 运行测试

| 命令 | 用途 | 前置条件 |
|------|------|----------|
| `make test-core-unit` | 运行核心层单元测试 | 无 |
| `make test-core-integration` | 运行核心层集成测试 | Docker 服务启动 |
| `make test-core-all` | 运行核心层所有测试 | Docker 服务启动 |
| `make test-core-coverage` | 生成覆盖率报告 | 无 |

### 测试编写规范

| 规范 | 说明 |
|------|------|
| 测试文件命名 | `test_{模块名}.py` |
| 测试类命名 | `Test{功能名}` |
| 测试函数命名 | `test_{功能}_{场景}` |
| Mock 使用 | 使用 `conftest.py` 提供公共 fixture |
| 集成测试标记 | 使用 `@pytest.mark.integration` |

### Mock 示例

**测试 fixture**（在 `conftest.py` 中定义）：
- `mock_llm_client`：模拟 LLM 客户端
- `mock_memory_store`：模拟记忆存储
- `mock_tool_registry`：模拟工具注册表
- `test_agent_context`：测试 Agent 上下文

---

## 📋 最佳实践

### Agent 开发

| 要求 | 说明 |
|------|------|
| 无状态 | Agent 应该是无状态的，状态通过上下文传递 |
| 配置化 | Agent 应该支持配置化，所有参数通过配置传入 |
| 错误处理 | Agent 应该有完整的错误处理，返回有意义的错误信息 |
| 异步执行 | Agent 应该支持异步执行，不要阻塞主线程 |

### Skill 开发

| 要求 | 说明 |
|------|------|
| 纯函数 | Skill 应该是无副作用的纯函数，除非明确标记 |
| 幂等性 | Skill 应该支持幂等执行，多次执行结果一致 |
| 超时控制 | Skill 应该有超时控制，避免无限等待 |
| 输入验证 | Skill 应该验证输入参数，返回有意义的错误信息 |

### 工具开发

| 要求 | 说明 |
|------|------|
| 权限校验 | 工具应该支持权限校验，确保调用者有权限 |
| 超时控制 | 工具应该有超时控制，避免无限等待 |
| 日志记录 | 工具调用应该有日志记录，便于排查问题 |
| 输入验证 | 工具应该验证输入参数，防止注入攻击 |

### 记忆管理

| 要求 | 说明 |
|------|------|
| 定期清理 | 记忆应该定期清理过期数据，避免存储无限增长 |
| 语义检索 | 记忆检索应该使用语义相似度，提高检索准确性 |
| 容量限制 | 记忆应该有容量限制，避免占用过多资源 |
| 加密存储 | 敏感记忆应该加密存储，确保数据安全 |

---

## 🔧 常见问题排查

### Agent 问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| Agent 注册失败 | 注册表未初始化 | 1. 确保在应用启动时调用 `init_registry()`<br>2. 检查 Agent 名称是否已存在 |
| Agent 执行超时 | 任务执行时间过长 | 1. 增加 Agent 超时配置<br>2. 优化 Agent 执行逻辑<br>3. 检查是否有阻塞操作 |
| Agent 无响应 | LLM 调用失败或网络问题 | 1. 检查 LLM 配置<br>2. 检查网络连接<br>3. 查看日志中的错误信息 |

### Skill 问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| Skill 执行失败 | 输入参数不正确 | 1. 检查 Skill 输入参数<br>2. 查看错误日志 |
| Skill 超时 | 执行时间过长 | 1. 增加 Skill 超时配置<br>2. 优化 Skill 执行逻辑 |
| Skill 幂等性问题 | 重复执行结果不一致 | 1. 检查 Skill 是否有副作用<br>2. 确保输入相同结果一致 |

### 编排问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 工作流卡住 | 步骤执行失败或条件不满足 | 1. 检查工作流定义<br>2. 检查步骤执行日志<br>3. 检查条件表达式 |
| 循环无限执行 | 循环条件永远为真 | 1. 检查循环条件<br>2. 添加循环次数限制 |
| 并行执行失败 | 步骤之间有依赖 | 1. 检查步骤依赖关系<br>2. 确保并行步骤独立 |

### 记忆问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 记忆检索慢 | 索引未优化或数据量大 | 1. 检查索引配置<br>2. 清理过期记忆 |
| 记忆丢失 | 存储失败或过期清理 | 1. 检查存储配置<br>2. 增加记忆过期时间 |
| 记忆容量不足 | 存储空间不足 | 1. 清理过期记忆<br>2. 增加存储容量 |

---

## 📖 相关链接

- [← 返回核心层文档](../../index.md)
- [架构师指南 →](../architect/index.md)
- [运维指南 →](../ops/index.md)

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- 启动时 discovery/seed：`core/server.py`
- AgentContext：`core/harness/interfaces/agent.py`
- Agents：`core/apps/agents/*`
