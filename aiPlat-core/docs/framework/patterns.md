# Agent 设计模式（设计真值：以代码事实为准）

> ⚠️ **实现状态提示（As-Is）**：Phase 7 后大部分模式已接线。6 种模式中 ReAct/Planning/Multi-Agent 已通过 Loop 驱动；协调模式已包含 6 种（含 HierarchicalDelegation），并可接入 MultiAgent。  
> ✅ HITL（审批）已通过 ApprovalManager + HookPhase（PRE/POST_APPROVAL_CHECK）接入工具调用链路。  
> 完整状态参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。

> 基于 Claude Code、OpenDev 等行业实践总结的 6 种核心 Agent 设计模式

---

## 一、模式概览

| 模式 | 核心特点 | 适用场景 | 复杂度 | 实现状态 |
|------|---------|---------|--------|----------|
| **ReAct** | 思考-行动-观察循环 | 基础问答、多步推理 | ⭐⭐ | ✅ 已实现 |
| **Tool Use** | 调用外部工具扩展能力 | 信息查询、系统集成 | ⭐⭐ | ✅ 已实现 |
| **Reflection** | 自我审视并修正错误 | 代码审查、内容润色 | ⭐⭐⭐ | ✅ 已实现 |
| **Planning** | 任务分解与顺序执行 | 复杂任务、自动化流程 | ⭐⭐⭐⭐ | ✅ 已实现 |
| **Multi-Agent** | 多智能体协作 | 企业级系统、团队协作 | ⭐⭐⭐⭐⭐ | ✅ 已实现 |
| **Human-in-the-Loop** | 人工介入关键决策 | 金融交易、敏感操作 | ⭐⭐⭐ | ✅ 已实现 |

---

## 二、ReAct 模式

### 2.1 核心概念

ReAct (Reasoning + Acting) 是 Agent 最基础的模式，核心是"思考-行动-观察"的循环：

```
1. 推理 (Reason) → 决定下一步做什么
2. 行动 (Act)    → 调用工具执行
3. 观察 (Observe) → 查看执行结果
4. 循环 → 回到步骤1，直到任务完成
```

### 2.2 工作流程

```
┌─────────────────────────────────────────────────────┐
│                    用户输入                          │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │   LLM 推理   │  ← 决定调用哪个工具
              └──────┬───────┘
                     │
         ┌───────────┴───────────┐
         ▼                           ▼
   ┌─────────────┐           ┌─────────────┐
   │ 需要工具调用 │           │ 直接回答    │
   └──────┬──────┘           └──────┬──────┘
          │                         │
          ▼                         ▼
   ┌──────────────┐           ┌──────────────┐
   │ 执行工具     │           │ 输出最终答案 │
   │ (Tool Call)  │           │   (Finish)   │
   └──────┬───────┘           └──────────────┘
          │
          ▼
   ┌──────────────┐
   │ 观察结果     │  ← 将工具返回结果加入上下文
   └──────┬───────┘
          │
          └──────────────┐
                         ▼
                    回到 LLM 推理
```

### 2.3 实现示例

```python
# 基于 ReAct 模式的 Agent 伪代码
class ReActAgent:
    def __init__(self, model, tools):
        self.model = model
        self.tools = tools
    
    async def run(self, task):
        messages = [{"role": "user", "content": task}]
        
        while True:
            response = await self.model.chat(messages)
            
            # 检查是否需要调用工具
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = tool_call.function.arguments
                    
                    # 执行工具
                    result = await self.tools.execute(tool_name, tool_args)
                    
                    # 将结果加入上下文
                    messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call.id
                    })
            else:
                # 无需工具调用，任务完成
                return response.content
```

### 2.4 适用场景

- 智能客服基础问答
- 需要多步推理的复杂问题
- 工具调用较少的简单任务
- 需要调试的 Agent 原型开发

---

## 三、Tool Use 模式

### 3.1 核心概念

Tool Use (也称 Function Calling) 让 Agent 具备"动手能力"，通过调用外部函数扩展能力边界。

**关键设计**：不是让模型自己执行操作，而是告诉模型有哪些工具可用，由模型决定何时调用。

### 3.2 工具定义规范

```yaml
# 工具定义示例
tools:
  - name: query_order
    description: 查询订单状态
    parameters:
      type: object
      properties:
        order_id:
          type: string
          description: 订单号
      required: [order_id]
  
  - name: get_weather
    description: 查询城市天气
    parameters:
      type: object
      properties:
        city:
          type: string
          description: 城市名称
      required: [city]
```

### 3.3 ACI 原则 (Agent-Computer Interface)

来自 Harness Engineering 实践：

| 原则 | 说明 | 示例 |
|------|------|------|
| **第一代** | 封装细粒度 API | 给 Agent 3个 API，自己协调 |
| **第二代** | ACI - 工具对应业务目标 | 一次调用完成一个目标 |
| **第三代** | 动态工具发现 + 示例驱动 | 按需加载，90%准确率 |

### 3.4 实现示例

```python
# 工具注册与调用
class ToolUseAgent:
    def register_tools(self, tool_registry):
        self.tools = tool_registry
    
    async def execute(self, tool_call):
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        
        # 查找并执行工具
        tool = self.tools.get(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}"
        
        return await tool.execute(**tool_args)
```

### 3.5 适用场景

- 信息查询（天气、股票、订单）
- 数据库操作
- API 调用集成
- 需要与外部系统交互的任务

---

## 四、Reflection 模式

### 4.1 核心概念

Reflection 模式让 Agent 具备"自我审视"能力，通过双 Agent 协作提升输出质量：

- **Executor Agent**：负责生成回答
- **Critic Agent**：负责检查质量并提出改进建议
- **循环迭代**：直到 Critic 通过或达到最大迭代次数

### 4.2 工作流程

```
用户输入
    │
    ▼
┌─────────────────┐
│ Executor Agent  │ ──→ 生成回答
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Critic Agent  │ ──→ 评审质量
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
  通过      不通过
    │         │
    ▼         ▼
  输出    ┌─────────────────┐
          │ 改进建议 + 重试  │
          └────────┬────────┘
                   │
                   └──────→ 回到 Executor
```

### 4.3 Critic Prompt 设计

```
你是一个质量检查专家。检查以下回答的质量：
- 事实准确性
- 逻辑完整性
- 表达清晰度
- 格式规范性

如果回答完美，回复 "PASS"。
如果有问题，明确指出需要改进的地方。
```

### 4.4 适用场景

- 代码审查
- 内容润色和优化
- 学术论文撰写
- 高准确度要求的问答

### 4.5 实现

> **代码位置**: `core/harness/execution/langgraph/graphs/reflection.py`

| 组件 | 说明 |
|------|------|
| `ReflectionConfig` | 配置：max_iterations, executor_model, critic_model, 评估维度 |
| `ReflectionState` | 状态：task, executor_output, critic_result, iteration, status |
| `ReflectionGraph` | 核心图：Executor 生成 → Critic 评价 → 通过/迭代 |
| `EvaluationDimension` | 评估维度：FACTUALITY, COMPLETENESS, CLARITY, FORMAT |
| `CriticResult` | 评价结果：passed, dimensions, feedback, summary |
| `create_reflection_graph()` | 工厂方法 |

---

## 五、Planning 模式

### 5.1 核心概念

Planning 模式将复杂任务分解为可执行的子任务，按顺序或并行执行。

**核心思想**：分而治之 (Divide and Conquer)

### 5.2 任务分解策略

| 策略 | 说明 | 示例 |
|------|------|------|
| **顺序分解** | 子任务按顺序执行 | 数据采集 → 分析 → 报告 |
| **并行分解** | 子任务同时执行 | 同时查询多个数据源 |
| **分层分解** | 多级任务树 | 大任务 → 子任务 → 子子任务 |

### 5.3 工作流程

```
用户："生成2026年Q1销售分析报告"
    │
    ▼
┌─────────────────┐
│  任务规划器     │ ──→ 分解为子任务
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│数据采集│ │数据分析│ │报告生成│
└───┬────┘ └───┬────┘ └───┬────┘
    │         │         │
    └────┬────┴────┬─────┘
         ▼
    ┌──────────┐
    │ 最终报告  │
    └──────────┘
```

### 5.4 实现示例

```python
class PlanningAgent:
    async def plan(self, task):
        # 1. 任务分解
        subtasks = await self.decompose(task)
        
        # 2. 执行子任务
        results = []
        for subtask in subtasks:
            result = await self.execute_subtask(subtask)
            results.append(result)
        
        # 3. 结果汇总
        final_report = await self.aggregate(results)
        return final_report
    
    async def decompose(self, task):
        # 使用 LLM 分解任务
        prompt = f"将以下任务分解为可执行的子任务：{task}"
        response = await self.model.chat(prompt)
        return self.parse_subtasks(response)
```

### 5.5 适用场景

- 数据分析全流程
- 自动化调研
- 复杂报告生成
- 项目规划与管理

### 5.6 实现

> **代码位置**: `core/harness/execution/langgraph/graphs/planning.py`

| 组件 | 说明 |
|------|------|
| `PlanningConfig` | 配置：strategy, model, max_depth, max_total_steps, max_parallel |
| `PlanningState` | 状态：task, subtasks, completed_ids, results, final_result |
| `PlanningGraph` | 核心图：Decompose → Execute → Aggregate |
| `SubTask` | 子任务：task_id, description, dependencies, status, priority |
| `DecompositionStrategy` | 分解策略：SEQUENTIAL, PARALLEL, HIERARCHICAL |
| `create_planning_graph()` | 工厂方法 |

---

## 六、Multi-Agent 模式

### 6.1 核心概念

Multi-Agent 模式让多个专业 Agent 协同工作，每个 Agent 有独立职责，通过消息通信实现协作。

### 6.2 协作模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **层级指挥** | 主 Agent 分解任务，子 Agent 执行 | 企业级任务调度 |
| **嵌套模式** | Agent 内部包含子 Agent | 复杂分层系统 |
| **转交模式** | 无法处理时转交其他 Agent | 客服升级场景 |
| **群聊模式** | 多个 Agent 自由讨论 | 创意头脑风暴 |

### 6.3 消息通信机制

```
┌─────────────────────────────────────────┐
│            MsgHub (消息中枢)             │
└────────┬────────┬────────┬───────────────┘
         │        │        │
         ▼        ▼        ▼
    ┌────────┐ ┌────────┐ ┌────────┐
    │Order   │ │Payment │ │Refund  │
    │ Agent  │ │ Agent  │ │ Agent  │
    └────────┘ └────────┘ └────────┘
    
Order Agent: "发现订单状态为已支付"
    │
    ▼ 发布消息 "payment:check"
MsgHub ──→ 转发给 Payment Agent
    │
    ▼ Payment Agent: "检查支付状态"
```

### 6.4 Subagent 权限控制

```yaml
# Subagent 配置示例
subagents:
  - name: secure-reviewer
    description: 安全审计专家
    tools: [Read, Grep, Glob]        # 只读工具
    disallowed_tools: [Write, Edit, Bash]  # 禁止修改
  
  - name: debugger
    description: 调试专家
    tools: [Read, Edit]             # 可修改现有文件
    disallowed_tools: [Write, Bash]  # 禁止创建新文件
```

### 6.5 适用场景

- 大型企业系统
- 多部门协同业务
- 复杂流程自动化
- 需要专业分工的任务

---

## 七、Human-in-the-Loop 模式

### 7.1 核心概念

Human-in-the-Loop (HITL) 将人工介入引入 Agent 决策闭环，关键节点需要人工确认。

**核心理念**：不是所有决策都交给 AI，涉及资金、权限、敏感数据的操作必须人工审批。

### 7.2 审批触发条件

| 条件类型 | 示例 | 处理方式 |
|---------|------|----------|
| **金额阈值** | 转账 > 10000 元 | 人工审批 |
| **敏感操作** | 删除数据、修改权限 | 人工审批 |
| **批量操作** | 批量删除、批量修改 | 人工审批 |
| **首次操作** | 首次执行某类操作 | 人工审批 |

### 7.3 工作流程

```
用户请求
    │
    ▼
┌─────────────────┐
│  Agent 分析意图  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 需要审批   不需要
    │         │
    ▼         ▼
┌─────────┐  ┌─────────────┐
│ 审批请求 │  │ 自动执行    │
└────┬────┘  └─────────────┘
     │
     ▼
┌─────────┐
│ 人工确认 │  ← 等待用户审批
└────┬────┘
     │
     ▼
┌────────┐     ┌────────┐
│ 拒绝   │     │ 执行   │
└────────┘     └────────┘
```

### 7.4 适用场景

- 金融交易处理
- 权限变更管理
- 敏感数据操作
- 合规要求严格的业务流程

### 7.5 实现

> **代码位置**: `core/harness/infrastructure/approval/`

| 组件 | 说明 |
|------|------|
| `ApprovalRule` | 审批规则：rule_id, rule_type, condition, threshold |
| `ApprovalRequest` | 审批请求：request_id, user_id, operation, status |
| `ApprovalResult` | 审批结果：decision, comments, approved_by |
| `ApprovalContext` | 审批上下文：session_id, operation, amount, batch_size |
| `RuleType` | 规则类型：AMOUNT_THRESHOLD, SENSITIVE_OPERATION, BATCH_OPERATION, FIRST_TIME |
| `ApprovalManager` | 核心管理器：register_rule, check_approval_required, approve, reject |
| `create_approval_manager()` | 工厂方法（含默认审批规则） |

**与 Hook 系统集成**：

| HookPhase | 说明 |
|-----------|------|
| `PRE_APPROVAL_CHECK` | 执行前审批检查 |
| `POST_APPROVAL_CHECK` | 执行后审批确认 |

---

## 八、模式组合使用

在实际项目中，这 6 种模式往往组合使用：

| 组合 | 说明 |
|------|------|
| **智能客服** | ReAct + Tool Use + Reflection |
| **数据分析平台** | Planning + Multi-Agent + Human-in-the-Loop |
| **代码助手** | ReAct + Tool Use + Reflection + Subagent |
| **企业工作流** | Planning + Multi-Agent + Human-in-the-Loop |

---

## 九、相关文档

- [Skill 生命周期](./skills/lifecycle.md) - Skill 的进化与管理
- [Context 管理](./harness/context.md) - 上下文压缩与记忆架构
- [Harness 基础设施](./harness/index.md) - 运行时系统设计

---

*最后更新: 2026-04-14*
