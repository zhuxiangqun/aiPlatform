# 多智能体协调 (Coordination)（设计真值：以代码事实为准）

> ✅ **实现状态提示（As-Is）**：Phase 7 已将 **6 种**协调模式接入（通过 patterns + agent adapter），并已将 `ConvergenceDetector` 接入 LangGraph `MultiAgentGraph` 的收敛评估路径。完整状态参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。
>
> ⚠️ **仍需注意（As-Is）**：
> - `MultiAgent` 在执行上仍存在“pattern 路径 + fallback 路径”两套实现（语义可能漂移）；设计文档需明确该降级策略与验收标准。

> 多智能体系统的协作模式——让多个 Agent 高效协同工作。

---

## 一句话定义

**多智能体协调是 Harness 的进程间通信**——通过不同的协作模式，实现复杂任务的多 Agent 高效协同。

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **协作模式** | 多 Agent 之间的任务分配与结果汇总方式 |
| **通信协议** | Agent 之间传递信息的方式 |
| **状态同步** | 多 Agent 共享任务进度和状态 |
| **结果聚合** | 将多个 Agent 的输出合并为最终结果 |

---

## 协作模式

> **实现说明**：所有 6 种协作模式在 `coordination/patterns/base.py` 中实现，通过工厂函数 `create_pattern()` 创建；Pattern 约定 `agent.execute(task: str)`，真实 Agent（`execute(AgentContext)`）需先经适配器包装。

---

## 证据索引（Evidence Index｜抽样）

- 协作模式实现与注册：`core/harness/coordination/patterns/base.py`（`create_pattern()` / `HierarchicalDelegationPattern`）
- MultiAgent 接入 patterns + fallback：`core/apps/agents/multi_agent.py`（`_pattern.coordinate()` / `_execute_parallel()`）
- ConvergenceDetector（LangGraph 路径）：`core/harness/execution/langgraph/graphs/multi_agent.py`（`_evaluate_convergence()`）

### 1. Pipeline（流水线）

任务按顺序经过多个 Agent，每个 Agent 处理特定环节。

```
User → Agent1 → Agent2 → Agent3 → Result
      (规划)   (执行)   (验证)
```

**适用场景**：流程化任务，每个环节需不同专业能力

**实现要点**：按顺序调用各 Agent，将输出作为下一个 Agent 的输入

### 2. Fan-out/Fan-in（并行处理）

多个 Agent 同时处理子任务，结果汇总。

```
          ┌─ Agent1 ─┐
User ────▶│  Agent2  │───▶ Aggregator ──▶ Result
          └─ Agent3 ─┘
```

**适用场景**：可分解的并行任务，如批量代码审查

**实现要点**：分解任务为子任务，并行执行后汇总结果

### 3. Expert Pool（专家池）

动态选择最合适的 Agent 处理当前任务。

```
User → Router → ┌─ Agent1 (前端专家)
                 │─ Agent2 (后端专家)
                 │─ Agent3 (DevOps)
                 └─ Agent4 (测试)
```

**适用场景**：需要多种专业能力的复杂任务

**实现要点**：基于任务特征选择合适的专家 Agent

### 4. Producer-Reviewer（生成+审核）

一个 Agent 生成结果，另一个 Agent 审核。

```
Generator ──▶ Reviewer ──▶ User
   ↓            ↓ (通过)
  修改         拒绝
```

**适用场景**：质量要求高的任务，需要二次验证

**实现要点**：生成结果后进行审核，根据审核结果决定是否重做

### 5. Supervisor（中心化调度）

一个 Supervisor 协调多个 Worker Agent。

```
┌─ Worker1
Supervisor ──▶ Worker2 ──▶ 结果
└─ Worker3
```

**适用场景**：需要统一调度的复杂任务

**实现要点**：Supervisor 负责规划、分配任务、聚合结果

### 6. Hierarchical Delegation（层级任务拆解）

任务逐层向下拆解，直到可执行为止。

```
Level1 (CEO)
   └─ Level2 (Manager1) ──▶ Agent1
       └─ Level2 (Manager2) ──▶ Agent2
                               └─ Agent3
```

**适用场景**：大型项目的层级分解

**实现要点**：递归拆解任务直到可执行，底层 Agent 完成后逐层汇总

---

## TriAgent 模式（规划-生成-评估）

> Anthropic 验证的高效模式——Planner/Generator/Evaluator 三代理各司其职
> 
> **详细说明**：见 [Harness 文档 - Evaluator Architecture](./index.md#95-evaluator-architecture评估器架构)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Planner   │───▶│  Generator  │───▶│  Evaluator  │
│  需求扩展   │    │   增量实现   │    │   动态测试   │
└─────────────┘    └─────────────┘    └─────────────┘
     ↑                   │                   │
     │                   ↓                   ↓
     │            ┌─────────────┐    ┌─────────────┐
     │            │Sprint 合约  │◀───│ 评分+反馈   │
     │            │ (谈判锁定)  │    │             │
     │            └─────────────┘    └─────────────┘
     └────────────────────────────────────────────┘
              谈判失败 → 重协商
```

| 代理 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **Planner** | 需求扩展、规格定义 | 1-4句用户提示 | 完整产品规格 |
| **Generator** | 增量实现、代码编写 | 规格 + Sprint合约 | 功能代码 |
| **Evaluator** | 动态测试、质量评分 | 运行中的应用 | 评分 + 缺陷报告 |

**适用场景**：复杂应用开发（DAW、游戏制作器、Web应用）

**核心优势**：
- 专业分工：每个代理只做一件事
- 对抗式质量保证：Evaluator 是严格的"评判者"
- Sprint 合同机制：双方通过"谈判"锁定验收标准

### 文件化通信模式

> 智能体之间通过文件传递信息，而非直接对话——结构化、便于审计、可纳入版本控制

| 文件 | 写入者 | 读取者 | 用途 |
|------|--------|--------|------|
| `spec.md` | Planner | Generator | 产品规格 |
| `sprint_report.md` | Generator | Evaluator | 实现报告 |
| `feedback.md` | Evaluator | Generator | 评估反馈 |

---

## 四维评分体系（Evaluator 核心）

> 评估器对生成器产出的评分维度——源自 Anthropic 的对抗式架构设计

| 维度 | 权重 | 说明 | 评估要点 |
|------|------|------|---------|
| **设计质量** | 30% | 设计是否作为连贯整体存在 | 布局逻辑、视觉层次、用户体验 |
| **原创性** | 25% | 是否避免"AI 审美惰性" | 定制化决策、创意突破 |
| **工艺水准** | 20% | 技术执行质量 | 排版、间距、色彩、代码质量 |
| **功能性** | 25% | 独立于美学的可用性 | 按钮可点击、表单可提交、功能可用 |

**权重分配策略**：
- 故意将设计质量和原创性权重设置得高于工艺和功能
- 因为 Claude 在工艺和功能上默认表现就不错
- 但在设计品味和原创性上倾向于生成"安全、可预测、视觉平庸"的布局

---

## 收敛检测

> 检测任务是否达到收敛状态

| 检测器 | 说明 |
|--------|------|
| **ConvergenceDetector** | 检测多 Agent 结果是否收敛到一致 |
| **LoopLevel** | 循环层级检测 |

---

## 通信协议

| 协议 | 特点 | 适用场景 |
|------|------|---------|
| **同步调用** | 阻塞等待结果 | 简单任务 |
| **异步消息** | 非阻塞，结果通过回调 | 并行任务 |
| **共享状态** | 通过公共存储共享 | 长期任务 |
| **事件驱动** | 基于事件触发 | 响应式任务 |

---

## 状态同步策略

> 多 Agent 共享任务进度和状态的机制

**关键要素**：
- **任务ID**：唯一标识任务
- **当前阶段**：任务执行阶段
- **已完成 Agent**：已完成的 Agent 列表
- **部分结果**：各 Agent 的输出
- **检查点**：执行过程中的状态快照

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| 执行系统 | 协作模式基于执行循环实现 |
| 记忆系统 | 会话续存支持跨 Agent 状态传递 |
| 工具系统 | Agent 可调用其他 Agent 作为工具 |
| Hooks | Stop Hook 可触发结果验证 |

---

## 相关文档

- [Harness 索引](./index.md) - Harness 完整定义
- [执行系统](./execution.md) - Agent 循环执行
- [观察系统](./observability.md) - 状态监控

> **代码示例**：协调系统的代码示例请参考 [开发者指南](./by-role/developer/index.md)

---

*最后更新: 2026-04-14*
