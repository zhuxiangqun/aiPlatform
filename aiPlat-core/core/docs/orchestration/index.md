# 编排层 (Orchestration Layer)

> 企业AI平台的任务规划、Agent协调和流水线执行的统一架构。

## 三层架构

```
┌───────────────────────────────────────────────────────┐
│              Orchestration Layer                        │
├───────────────────────────────────────────────────────┤
│  L1 Planning     IntentAnalyzer → ChainPlanner         │
│    (规划层)        → CapabilityMapper → Orchestrator    │
│                    → DAG 计划输出                       │
│                 位置: core/orchestration/               │
│                 约束: 无副作用，仅产出计划               │
├───────────────────────────────────────────────────────┤
│  L2 Coordination  8 种协调模式                          │
│    (协调层)        Pipeline / FanOutFanIn / Supervisor  │
│                  ExpertPool / ProducerReviewer          │
│                  HierarchicalDelegation / Sequential     │
│                  位置: core/harness/coordination/        │
│                  约束: 协调但不直接执行工具               │
├───────────────────────────────────────────────────────┤
│  L3 Execution     PipelineEngine + LangGraph            │
│    (执行层)        + SubagentCoordinator                │
│                   + ParallelExecutor                    │
│                  位置: harness/execution/ + apps/agents/ │
│                  约束: 必须通过 ReActLoop syscall 路径    │
└───────────────────────────────────────────────────────┘
```

| 层 | 职责 | 核心组件 | 代码位置 |
|------|------|------|------|
| **L1 规划** | 意图分析、任务拆分、能力映射、DAG生成 | `IntentAnalyzer`, `ChainPlanner`, `CapabilityMapper`, `Orchestrator` | `core/orchestration/` |
| **L2 协调** | Agent间通信、结果聚合、失败恢复、模式选择 | 8 patterns: `PipelinePattern`, `FanOutFanInPattern`, `SupervisorPattern`, `ExpertPoolPattern`, `ProducerReviewerPattern`, `HierarchicalDelegationPattern` | `core/harness/coordination/patterns/` |
| **L3 执行** | DAG执行、checkpoint、重试、SubAgent调度、并行执行 | `PipelineEngine`, `LangGraph`, `SubagentCoordinator`, `ParallelExecutor` | `core/harness/execution/` + `core/apps/agents/` |

## 编排模式

| 模式 | 适用场景 | 说明 |
|------|---------|------|
| **Pipeline** | 顺序任务（A→B→C） | 步骤确定，上下游依赖 |
| **FanOutFanIn** | 并行子任务→汇总 | 独立任务并发执行，结果聚合 |
| **Supervisor** | 中心调度器→Worker→聚合 | 主Agent拆任务，Worker执行，主Agent汇总 |
| **ExpertPool** | 按能力路由到专家Worker | 多个专家Worker，按任务类型自动选择 |
| **ProducerReviewer** | 生成→审查→修改循环 | 多轮质量迭代 |
| **HierarchicalDelegation** | 多层嵌套SubAgent | 复杂场景的分层决策 |

## Single-Agent ↔ Multi-Agent 渐进演进

系统支持从简单到复杂的渐进式演进：

1. **起步** — 用 `ConversationalAgent` / `ReActAgent` 跑通 MVP
2. **发现瓶颈** — 从 Trace 日志找到上下文/专业/并行瓶颈
3. **拆 Worker** — 为每个瓶颈创建专用 `Subagent`，配置独立 tools/prompts/permissions
4. **选模式** — 配置 `MultiAgent` + `coordination_pattern`（如 supervisor）
5. **演进完成** — Orchestrator 自动调度，Worker 专注执行

**核心原则**：每拆一个 Worker 必须能回答"它解决了哪个明确瓶颈？"——如果回答不出来，不拆。

## 统一入口

```python
from core.orchestration import *

# 规划：意图→任务拆分→DAG
plan = Orchestrator().plan_intent("帮我写一份 AI 行业竞品分析")

# 协调：选择模式 + 执行
pattern = create_pattern("supervisor")
result = await pattern.execute(plan, workers)

# 执行：PipelineEngine 直接运行 DAG
engine = PipelineEngine(config)
await engine.run(plan.to_stages())
```

## 与其他层的关系

| 依赖 | 方向 |
|------|------|
| Harness 执行引擎 | 编排层 L3 的基础——ReAct 循环是所有执行的基础 |
| Agent 系统 | 编排层 L3 的 Worker 来源——每个 Agent 可作为一个 Worker |
| 本体引擎 | 编排层 L1 的任务目标来源——意图分析基于本体类识别 |
| 记忆子系统 | 编排层 L3 的上下文基础——SubAgent 间通过记忆共享状态 |
| Skill 系统 | 编排层 L3 的工具来源——Worker 通过 Skill 完成任务 |

---

*最后更新: 2026-06-24*
