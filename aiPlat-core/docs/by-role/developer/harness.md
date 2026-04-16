# Harness 开发指南（设计真值：以代码事实为准）

> 说明：本文档的目录结构清单若与代码不一致，以代码事实为准。统一口径参见 [`ARCHITECTURE_STATUS.md`](../../ARCHITECTURE_STATUS.md)。

> 本文档为开发者提供 Harness 模块的开发指导，包括代码实现、API 使用、配置参数等。

---

## 概述

Harness 是智能体的基础设施框架，提供 Agent 的完整生命周期管理能力。

---

## 模块结构

```
harness/
├── __init__.py                    # Harness 入口
├── state.py                       # Agent 状态定义
├── heartbeat_monitor.py          # 心跳监控
├── integration.py                 # HarnessIntegration 统一入口
│
├── interfaces/                    # 接口定义层（子集）
│   ├── agent.py                   # IAgent, AgentConfig, AgentResult
│   ├── tool.py                    # ITool, ToolConfig, ToolResult
│   ├── skill.py                   # ISkill, SkillConfig, SkillResult
│   ├── loop.py                    # ILoop, LoopState, LoopResult
│   ├── coordinator.py             # ICoordinator
│   └── (To-Be)                     # IContext/IRouter/IAdapter 如需使用，应补齐实现与接线
│
├── execution/                      # 执行系统
│   ├── loop.py                     # 执行循环 (ReAct Loop)
│   ├── retry.py                    # 重试管理器
│   ├── policy.py                   # 执行策略
│   ├── feedback.py                 # 反馈机制
│   ├── langgraph/                  # LangGraph 编排
│   │   ├── core.py                 # 核心功能
│   │   ├── executor.py             # 图执行器
│   │   ├── callbacks.py             # 回调系统
│   │   ├── graphs/                  # 图定义
│   │   │   ├── react.py            # ReAct 图
│   │   │   ├── multi_agent.py      # MultiAgent 图
│   │   │   └── tri_agent.py       # TriAgent 图
│   │   └── nodes/                   # 节点定义
│   │       ├── reason_node.py      # 推理节点
│   │       ├── act_node.py         # 行动节点
│   │       └── observe_node.py     # 观察节点
│   └── executor/
│       └── unified.py               # 统一执行器
│
├── coordination/                   # 协调系统
│   ├── patterns/
│   │   └── base.py                 # 协作模式 (Pipeline, FanOut, etc.)
│   ├── coordinators/
│   │   └── agent.py                # Agent 协调器
│   └── detector/
│       └── convergence.py          # 收敛检测
│
├── observability/                  # 观察系统
│   ├── monitoring/                 # 监控
│   ├── metrics/                    # 指标
│   ├── events/                     # 事件
│   └── alerts/                     # 告警
│
├── feedback_loops/                 # 反馈循环
│   ├── local.py                    # LOCAL 层
│   ├── push.py                     # PUSH 层
│   ├── prod.py                     # PROD 层
│   └── evolution_trigger.py        # 进化触发器
│
├── memory/                         # 记忆系统
│   ├── base.py                     # 记忆基类
│   ├── short_term.py               # 短期记忆
│   ├── long_term.py                # 长期记忆
│   ├── session.py                  # 会话管理
│   └── langchain_adapter.py        # LangChain 适配器
│
├── knowledge/                      # 知识系统
│   ├── types.py                    # 知识类型
│   ├── retriever.py                # 知识检索
│   ├── indexer.py                  # 知识索引
│   └── evolution.py                # 知识进化
│
└── infrastructure/                 # 基础设施
    ├── langchain/                  # LangChain 集成
    │   ├── models.py               # 模型集成
    │   ├── tools.py                 # 工具集成
    │   └── prompts.py               # 提示词集成
    ├── config/
    │   └── settings.py             # 配置
    ├── lifecycle/
    │   └── manager.py               # 生命周期
    ├── hooks/
    │   └── hook_manager.py          # 钩子系统
    ├── bootstrap/
    │   └── __init__.py              # 启动引导
    └── di/
        └── __init__.py              # 依赖注入
```

---

## 核心类

### HarnessIntegration

统一入口，管理所有 Harness 组件：

```python
from core.harness import HarnessIntegration, create_harness

# 创建 Harness 实例
harness = create_harness()

# 或获取单例
harness = HarnessIntegration.get_instance()

# 启动
await harness.start()

# 访问组件
harness.monitoring   # 监控系统
harness.metrics      # 指标收集
harness.event_bus    # 事件总线
harness.alert_manager # 告警管理
harness.feedback     # 本地反馈
harness.memory       # 记忆系统

# 停止
await harness.stop()
```

### Agent 状态

```python
from core.harness import AgentState, AgentStateEnum

# 状态枚举
class AgentStateEnum(Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    TERMINATED = "terminated"
```

### 心跳监控

```python
from core.harness import HeartbeatMonitor, heartbeat_monitor

# 使用单例
monitor = heartbeat_monitor

# 注册 Agent
monitor.register(agent_id="agent-1", agent=my_agent)

# 更新心跳
monitor.update_heartbeat("agent-1")

# 获取状态
status = monitor.get_status("agent-1")
```

---

## 执行系统

### ReAct 循环

```python
from core.harness.execution import ReActLoop, create_loop

# 创建循环
loop = create_loop("react", agent=my_agent)

# 执行
result = await loop.run(context)  # As-Is：Loop 接口为 run()/step()
```

### LangGraph 编排

```python
from core.harness.execution.langgraph import (
    GraphBuilder,
    CompiledGraph,
    create_graph_builder,
)

# 构建图
builder = create_graph_builder("my_graph")
builder.add_node("start", start_node)
builder.add_node("process", process_node)
builder.add_node("end", end_node)
builder.add_edge("start", "process")
builder.add_edge("process", "end")
builder.set_entry_point("start")
builder.add_end_point("end")

# 编译执行
graph = builder.build()
result = await graph.execute(initial_state)
```

### 回调系统

```python
from core.harness.execution.langgraph import (
    CallbackManager,
    create_callback_manager,
)

# 创建回调管理器
manager = create_callback_manager()

# 注册回调
manager.on_node_start(my_callback)
manager.on_node_end(my_callback)

# 触发
await manager.trigger_node_start("my_graph", "node_name", state)
```

---

## 协调系统

### 协作模式

```python
from core.harness.coordination import (
    create_pattern,
    PipelinePattern,
    FanOutFanInPattern,
    ExpertPoolPattern,
)

# 创建流水线模式
pattern = create_pattern("pipeline")
pattern.add_step(agent1)
pattern.add_step(agent2)
results = await pattern.execute(context)

# 创建并行模式
pattern = create_pattern("fan_out_fan_in")
pattern.add_agent(agent1)
pattern.add_agent(agent2)
results = await pattern.execute(context)
```

---

## 观察系统

### 监控

```python
from core.harness.observability import MonitoringSystem

monitoring = MonitoringSystem.get_instance()

# 注册指标
metric = monitoring.register_metric("request_count", MetricType.COUNTER)

# 记录
monitoring.increment("request_count")

# 注册目标
monitoring.register_target("db", check_fn=lambda: db.is_healthy())

# 启动监控
await monitoring.start_monitoring()
```

### 事件总线

```python
from core.harness.observability import EventBus, EventType

event_bus = EventBus.get_instance()

# 订阅事件
async def my_handler(event):
    print(f"Got event: {event}")

event_bus.subscribe(EventType.AGENT_STARTED, my_handler)

# 发布事件
event_bus.emit(
    EventType.AGENT_STARTED,
    source="my_agent",
    data={"status": "running"}
)
```

---

## 记忆系统

```python
from core.harness.memory import (
    ShortTermMemory,
    LongTermMemory,
    SessionManager,
)

# 短期记忆
short_term = ShortTermMemory({"max_size": 100})
await short_term.store(entry)

# 长期记忆
long_term = LongTermMemory()
await long_term.store(entry)

# 会话管理
session_mgr = SessionManager()
session = await session_mgr.create_session()
```

---

## 知识系统

```python
from core.harness.knowledge import (
    KnowledgeRetriever,
    KnowledgeIndexer,
    KnowledgeType,
    create_retriever,
)

# 创建检索器
retriever = create_retriever()

# 搜索
results = await retriever.search("我的问题", limit=5)

# 添加知识
await retriever.add_knowledge(
    content="这是一条知识",
    title="知识标题",
    knowledge_type=KnowledgeType.DOCUMENT,
)
```

---

## 反馈循环

```python
from core.harness.feedback_loops import (
    LocalFeedbackLoop,
    PushManager,
    ProductionFeedbackLoop,
    EvolutionEngine,
)

# 本地反馈
local_feedback = LocalFeedbackLoop()
local_feedback.success("agent-1", "任务成功")

# 推送通知
push_mgr = PushManager()
await push_mgr.register_target("webhook", "https://...")
await push_mgr.emit("agent-1", "task_complete", {"result": "success"})

# 进化触发
evolution = EvolutionEngine()
await evolution.on_error_threshold(error_rate=0.1, threshold=0.05)
```

---

## 相关文档

- [Harness 索引](../../harness/index.md) - Harness 完整定义
- [执行系统](../../harness/execution.md) - Agent 循环执行
- [协调系统](../../harness/coordination.md) - 多 Agent 协作
- [观察系统](../../harness/observability.md) - 状态监控

---

*最后更新: 2025-01-14*

---

## 证据索引（Evidence Index｜抽样）

- HarnessIntegration：`core/harness/integration.py`
- Loop-first：`core/harness/execution/loop.py`
- LangGraph：`core/harness/execution/langgraph/*`
