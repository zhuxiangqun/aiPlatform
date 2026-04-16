# 应用层 (Apps)（设计真值：以代码事实为准）

> 应用层包含 Agent、Skill、Tool 的具体实现，基于 Harness 操作系统层构建。

---

## 一句话定义

**应用层是 Harness 的具体实现层**——提供各类 Agent、Skill、Tool 的具体实现，依赖 Harness 提供的框架能力。

---

## 目录结构（As-Is）

```
core/apps/
├── agents/                         # Agent 实现
│   ├── base.py                   # Agent 基类
│   ├── react.py                  # ReAct Agent
│   ├── plan_execute.py           # 规划执行 Agent
│   ├── conversational.py         # 对话 Agent
│   ├── rag.py                    # RAG Agent
│   └── multi_agent.py            # 多 Agent 协作
│
├── skills/                        # Skill 实现
│   ├── base.py                   # Skill 基类 + 内置技能
│   │   # - TextGenerationSkill
│   │   # - CodeGenerationSkill
│   │   # - DataAnalysisSkill
│   │   # - create_skill()
│   ├── registry.py               # SkillRegistry（版本管理、启用/禁用、绑定统计）
│   └── executor.py               # SkillExecutor（执行、超时控制、执行记录）
│
└── tools/                         # Tool 实现
    └── base.py                   # Tool 基类 + 内置工具 + ToolRegistry
        # - CalculatorTool
        # - SearchTool
        # - FileOperationsTool
        # - ToolRegistry (工具注册表)
```

---

## Agents 实现

### Agent 基类

**Agent 基类**

实现 `IAgent` 接口，提供 Agent 的基础实现：

- 依赖执行循环（ILoop）驱动执行
- 管理配置对象
- 提供初始化和清理的默认实现

### ReAct Agent

**ReAct Agent**

推理-行动智能体，基于 ReAct 执行循环实现：

- 推理阶段：LLM 决定下一步行动
- 行动阶段：执行工具调用
- 观察阶段：处理工具结果
- 适用于需要推理和工具调用的任务

### Plan-Execute Agent

**规划-执行 Agent**

先规划后执行的智能体：

- 规划阶段：分析任务，生成步骤计划
- 执行阶段：按计划顺序执行各步骤
- 适用于复杂任务，需要步骤分解

### Conversational Agent

**对话 Agent**

专注于多轮对话的智能体：

- 保持对话状态，支持上下文理解
- 支持多轮交互直到任务完成
- 适用于问答场景

### Reflection Agent

**自我审视 Agent**

基于自我审视和修正的智能体：

- 生成初始结果后进行自我评估
- 根据评估反馈迭代修正输出
- 适用于代码审查、内容润色、方案优化

> 详细设计模式见 [Agent 设计模式](../framework/patterns.md)

---

## 证据索引（Evidence Index｜抽样）

- Agents：`core/apps/agents/*`
- Skills：`core/apps/skills/*`
- Tools：`core/apps/tools/*`

### Planning Agent

**任务分解 Agent**

基于任务分解和计划执行的智能体：

- 将复杂任务分解为可执行的子任务
- 按计划顺序执行各子任务
- 适用于自动化流程、报告生成等场景

> 详细设计模式见 [Agent 设计模式](../framework/patterns.md)

### Multi-Agent

**多 Agent 协作**

协调多个 Agent 协同工作的智能体：

- 依赖协调器（ICoordinator）管理协作
- 管理多个子 Agent 实例
- 适用于需要多角色分工的复杂任务

---

## Skills 实现

### Skill 基类

**Skill 基类**

位于 `core/apps/skills/base.py`，实现 `ISkill` 接口，提供技能的基础实现：

- 执行具体逻辑
- 验证输入参数
- 子类实现具体业务逻辑

> 当前版本仅包含 Skill 基类，内置技能和注册/执行器将在后续版本实现。

---

## Tools 实现

### Tool 基类与内置工具

**Tool 基类**

位于 `core/apps/tools/base.py`，实现 `ITool` 接口，提供工具的基础实现：

- 执行具体工具逻辑
- 验证输入参数合法性
- 子类实现具体工具功能
- 内置编排追踪器自动注入
- 内置调用统计（call_count / success_count / error_count / avg_latency）
- 内置权限管理

### 内置工具

**CalculatorTool**：执行数学运算（加、减、乘、除等）

**SearchTool**：执行外部搜索查询

**FileOperationsTool**：读写、操作文件系统

### ToolRegistry 工具注册表

位于 `core/apps/tools/base.py`，提供全局工具注册表：

- 单例模式，线程安全
- 工具注册与注销
- 按名称/类别获取工具
- 自动注入编排追踪器和权限管理器

> 详细设计见 [工具系统文档](../tools/index.md)

---

## 与 Harness 的关系

| 应用层 | 依赖的 Harness 组件 |
|--------|-------------------|
| **agents** | interfaces/IAgent, execution/loop, execution/langgraph |
| **skills** | interfaces/ISkill |
| **tools** | interfaces/ITool, observability (追踪), infrastructure (权限) |

---

## 相关文档

- [Harness 索引](./harness/index.md) - Harness 完整定义
- [Harness 接口文档](./harness/interfaces.md) - 接口定义
- [执行系统文档](./harness/execution.md) - 执行循环

---

*最后更新: 2026-04-14*
