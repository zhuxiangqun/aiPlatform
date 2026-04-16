# Agent 架构设计（设计真值：以代码事实为准）

> ⚠️ **实现状态提示（As-Is vs To-Be）**：本文档以 **当前代码事实（As-Is）** 为准，并对尚未形成闭环的能力标注为 **To-Be**。  
> 完整状态与证据链参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。
>
> **Phase 7 已修复（As-Is）**：
> - ✅ ReActAgent/PlanExecuteAgent 委托 `super().execute()` → Loop 驱动执行
> - ✅ HeartbeatMonitor 通过 `asyncio.ensure_future` 启动
> - ✅ 状态模型已按 canonical（`AgentStateEnum`）收敛关键落点（management/registry 默认值与映射）
> - ✅ Manager↔Registry 通过 `_bridge_to_registry()` 桥接
> - ✅ RAGAgent import 修复 + _model 属性修复
>
> **仍需注意（As-Is）**：
> - ConversationalAgent 保留 execute() override（对话模式不需要 Loop，直接调 model）
> - Skill 版本回滚语义与 fork 执行模式已落地在执行层，但“技能目录化/manifest 化”仍属于 To-Be（详见 skills 文档）

> Agent 的核心架构设计，包括类型体系、生命周期、配置管理与执行模型

本文档是 [Agent 概述](./index.md) 的扩展，聚焦于架构层面的设计决策。

---

## 一、核心定位

Agent 是基于 Harness 构建的智能体实例，负责具体任务的执行。

**与 Harness 的关系**：
- Harness 提供基础设施（执行循环、心跳监控、协调协作）
- Agent 是 Harness 的具体应用，实现特定业务能力

**核心职责**：
- 任务理解与规划
- 工具/Skill 调用编排
- 状态管理与上下文维护
- 执行结果评估与反馈

---

## 二、类型体系

> 详细实现见 [Agent 设计模式](../framework/patterns.md)

| 类型 | 核心模式 | 适用场景 | 复杂度 |
|------|---------|---------|--------|
| **ReAct** | Reason + Act 循环 | 基础问答、多步推理 | ⭐⭐ |
| **Tool-Using** | 工具调用扩展能力 | 信息查询、系统集成 | ⭐⭐ |
| **Reflection** | 自我审视 + 修正 | 代码审查、内容润色 | ⭐⭐⭐ |
| **Planning** | 任务分解 + 顺序执行 | 复杂任务、自动化流程 | ⭐⭐⭐⭐ |
| **Multi-Agent** | 多智能体协作 | 企业级系统、团队协作 | ⭐⭐⭐⭐⭐ |
| **Human-in-the-Loop** | 人工介入关键决策 | 金融交易、敏感操作 | ⭐⭐⭐ |

> 详细的工作流程、协作模式、触发条件等请参考 [Agent 设计模式](../framework/patterns.md)，本文档不再重复。

---

## 三、生命周期

> 核心实现见 [Harness 智能体框架](./harness/index.md)

Agent 生命周期由 Harness 管理，状态流转如下：

```
CREATED → INITIALIZING → READY → RUNNING → PAUSED → STOPPED
                                           ↓
                                         ERROR → TERMINATED
```

| 状态 | 说明 | 关键行为 |
|------|------|----------|
| **CREATED** | 实例创建 | 配置加载、接口初始化 |
| **INITIALIZING** | 初始化中 | 资源分配、依赖注入 |
| **READY** | 就绪 | 等待任务触发 |
| **RUNNING** | 执行中 | 任务处理、状态更新 |
| **PAUSED** | 暂停 | 保留上下文、可恢复 |
| **STOPPED** | 停止 | 资源释放 |
| **ERROR** | 异常 | 错误记录、告警 |
| **TERMINATED** | 终止 | 完全清理 |

> 状态详细定义、心跳监控、健康分数计算等见 [Harness 执行系统](./harness/execution.md)

---

## 设计补全（Round2）：状态模型统一规范（必须收敛）

> 背景：状态模型若在 interfaces/harness/management/registry 多套并存，会导致监控、控制、恢复、前端展示出现语义错乱。

### 1) 单一真相（Canonical State）

**唯一标准生命周期枚举**建议以 Harness 生命周期为准（示例）：
`CREATED → INITIALIZING → READY → RUNNING → PAUSED → STOPPED → TERMINATED`（异常：ERROR）

### 2) 各层映射规则（必须定义并校验）

| 层 | 当前形态（示例） | 目标 | 要求 |
|---|---|---|---|
| interfaces | AgentStatus（短集合） | 作为运行态子集 | 必须能映射到 Canonical |
| harness | AgentLifecycleState/AgentStateEnum | Canonical | 唯一真相来源 |
| management | AgentInfo.status:str | 改为枚举或强制映射 | API 返回必须稳定 |
| registry | 内部状态字符串 | 改为 Canonical | 禁止任意字符串 |

### 3) API 契约（对外稳定字段）

对外接口建议统一返回：
- `status`（canonical）
- `status_reason`（可选）
- `last_transition_at`（可选）

### 4) 验收标准（必须有测试）

1. Agent 创建→初始化→执行→完成 的链路中，状态变化可追溯且单一一致
2. management API 返回的 status 只来自 canonical 集合


---

## 四、执行模型

### 4.1 执行流程

```
用户输入 → 意图理解 → 任务规划 → 执行循环 → 结果评估 → 输出
              ↓                                    ↓
         工具/Skill调用 ←──────────────────── 上下文更新
```

### 4.2 执行循环

> 详细实现见 [Harness 执行系统](./harness/execution.md)

Agent 执行基于 **ReAct 循环**：

```
推理 (Reason) → 行动 (Act) → 观察 (Observe) → 循环直到完成
```

**Hook 拦截点**：

| 阶段 | 拦截点 | 用途 |
|------|--------|------|
| 循环前 | PreLoop | 初始化状态 |
| 思考前 | PreReasoning | 准备思考 |
| 思考后 | PostReasoning | 验证推理 |
| 行动前 | PreAct | 准备工具调用 |
| 行动后 | PostAct | 验证工具结果 |
| 观察后 | PostObserve | 处理观察结果 |
| 循环后 | PostLoop | 清理和保存 |
| 任务完成前 | Stop | 强制验证 |

### 4.3 工具调用

> 详细实现见 [工具系统](./tools/index.md)

Agent 通过工具系统扩展能力：

```python
# 工具注册
tool_registry.register("web_search", WebSearchTool())
tool_registry.register("calculator", CalculatorTool())

# 工具调用
result = await agent.execute_tool("web_search", {"query": "天气"})
```

---

## 五、配置管理

### 5.1 配置结构

```python
from core.harness.interfaces import AgentConfig

config = AgentConfig(
    name="my-agent",
    type="ReAct",
    model="gpt-4",
    max_iterations=25,
    timeout_seconds=300,
    
    # 工具配置
    tools=["web_search", "calculator"],
    tool_choice="auto",  # auto / specific
    
    # 记忆配置
    memory={
        "type": "short_term",
        "recall_count": 5,
        "max_history": 100
    },
    
    # 执行策略
    retry={
        "enabled": True,
        "max_attempts": 3,
        "backoff": "exponential"
    }
)
```

### 5.2 模型参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `model` | 使用的模型 | gpt-4 |
| `temperature` | 采样温度 | 0.7 |
| `max_tokens` | 最大输出 token | 4096 |
| `top_p` | 核采样 | 1.0 |
| `stop` | 停止词 | [] |

### 5.3 工具绑定

> 与 [Skill 管理](../management/docs/core/skills.md) 的关系

Agent 可以绑定两类能力：
- **Tools**：外部工具（WebSearch, Calculator 等）
- **Skills**：业务技能（TextGeneration, CodeAnalysis 等）

获取绑定的技能：
```python
GET /api/core/agents/{agent_id}/skills
```

---

## 证据索引（Evidence Index｜抽样）

- Agent 执行委托 Loop：`core/apps/agents/base.py: BaseAgent.execute()`
- ReAct/PlanExecute 委托：`core/apps/agents/react.py` / `core/apps/agents/plan_execute.py`
- management 状态规范化：`core/management/agent_manager.py`（`AgentStateEnum` / `_normalize_status()`）
- registry 默认状态：`core/apps/agents/discovery.py`（默认 `ready`）

---

## 六、自我进化

> 详细实现见 [Harness 反馈循环](./harness/feedback-loops.md)

Agent 支持根据执行历史自动优化参数：

### 6.1 进化触发条件

| 条件 | 默认值 | 说明 |
|------|--------|------|
| 最小样本 | 10 次 | 需要积累足够执行数据 |
| 性能阈值 | 70% | 成功率低于此值触发优化 |
| 进化间隔 | 1 小时 | 避免频繁进化 |

### 6.2 进化内容

- **参数调整**：温度、top_p、max_tokens 等 LLM 参数
- **策略切换**：工具选择、记忆检索策略
- **能力扩展**：注册新技能、启用新工具

### 6.3 三层反馈循环

| 层级 | 说明 | 生效范围 |
|------|------|----------|
| **LOCAL** | 本地反馈，仅当前实例生效 | 开发/测试环境 |
| **PUSH** | 配置推送，版本管理 | 预发布环境 |
| **PROD** | 生产生效，全集群应用 | 生产环境 |

---

## 七、与模块的关系

| 模块 | 关系 | 引用 |
|------|------|------|
| **Harness** | 生命周期、执行循环、协调协作 | [Harness 框架](./harness/index.md) |
| **Tools** | 外部工具调用 | [工具系统](./tools/index.md) |
| **Skills** | 业务技能调用 | [技能系统](./skills/index.md) |
| **Memory** | 上下文与记忆管理 | [记忆系统](./memory/index.md) |
| **Knowledge** | RAG 知识检索 | [知识系统](./knowledge/index.md) |
| **Models** | LLM 模型调用 | [LLM 适配器](./adapters/llm.md) |

---

## 八、相关文档

- [Agent 概述](./index.md) - Agent 模块定位与类型
- [Agent 设计模式](../framework/patterns.md) - 6 种核心模式详解
- [Harness 智能体框架](./harness/index.md) - 基础设施层
- [执行系统](./harness/execution.md) - ReAct 循环与 LangGraph
- [工具系统](./tools/index.md) - 工具定义与调用
- [技能系统](./skills/index.md) - 技能定义与执行
- [记忆系统](./memory/index.md) - 上下文管理

---

*最后更新: 2026-04-14*
*版本: v1.0*
