# 智能体实现 (Agents)

> ⚠️ **实现状态提示**：Phase 7 已修复 Manager↔Registry 断开和 RAGAgent 错误。完整状态参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。

> 智能体实现模块提供各类预定义智能体的具体实现，是智能体框架的具体应用。

---

## 模块定位

Agents 模块基于 Harness 构建，提供智能体的具体实现类型。

**核心能力**：
- 各类智能体的具体实现
- 智能体配置与参数调优
- 智能体性能优化
- 智能体测试与评估

**详细架构设计**：[Agent 架构设计](./architecture.md)

---

## 智能体类型

| 类型 | 模式 | 适用场景 | 实现状态 |
|------|------|----------|----------|
| **ReAct Agent** | Reason + Act 循环 | 需要推理和工具调用的任务 | ✅ 已实现 |
| **Plan-Execute Agent** | 先规划后执行 | 复杂任务，需要步骤分解 | ✅ 已实现 |
| **Conversational Agent** | 对话模式 | 多轮交互，问答场景 | ✅ 已实现 |
| **Tool-Using Agent** | 工具为主 | 需要频繁调用外部工具 | ✅ 已实现 |
| **RAG Agent** | 检索+生成 | 需要知识库支持的回答 | ✅ 已实现 |
| **Multi-Agent** | 协作模式 | 复杂任务，需要多角色 | ✅ 已实现 |
| **Reflection Agent** | 自我审视+修正 | 代码审查、内容润色 | ✅ 已实现 |
| **Planning Agent** | 任务分解+执行 | 自动化流程、报告生成 | ✅ 已实现 |

> 详细的设计模式、工作流程、协作机制见 [Agent 设计模式](../framework/patterns.md)

---

## 设计原则

- 每个智能体应该有明确的职责边界
- 智能体之间应该通过消息通信
- 智能体应该支持插件化扩展
- 智能体应该支持自定义配置

---

## 自我进化能力

> **注意**：本节描述的是 **Agent 参数级别的自我进化**（如温度、top_p 等运行参数调优），与 [Skill 生命周期进化](../skills/lifecycle.md)（CAPTURED/FIX/DERIVED 模式）是不同层面的机制。
> Agent 进化关注"运行参数优化"，Skill 进化关注"能力定义迭代"。

智能体支持根据执行历史自动优化策略：

- **性能追踪**：自动记录执行成功/失败、耗时、资源消耗
- **策略进化**：根据性能数据调整 Agent 参数（温度、top_p、max_tokens 等）
- **阈值触发**：达到阈值时自动触发进化

### 反馈循环

详细机制见 [Harness 三层反馈循环](./harness/index.md#6-三层反馈循环系统)：

| 层级 | 说明 | 生效范围 |
|------|------|----------|
| **LOCAL** | 本地反馈，仅在当前实例生效 | 开发/测试环境 |
| **PUSH** | 配置推送，将优化推送到配置中心 | 预发布环境 |
| **PROD** | 生产生效，全集群应用优化 | 生产环境 |

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **harness** | 基于 Harness 的生命周期和执行循环 |
| **memory** | 使用记忆系统存储上下文 |
| **knowledge** | 使用知识库进行 RAG |
| **tools** | 调用工具执行具体操作 |
| **skills** | 调用技能完成任务 |

---

---

## 相关文档

- [Agent 架构设计](./architecture.md) - 详细架构（类型体系、生命周期、执行模型、配置管理）
- [Harness 索引](./harness/index.md) - 智能体框架
- [Harness 执行系统](./harness/execution.md) - Agent 循环执行
- [Harness 协调系统](./harness/coordination.md) - 多 Agent 协作
- [Agent 设计模式](../framework/patterns.md) - 6种核心模式
- [Skill 生命周期](../skills/lifecycle.md) - Skill 进化机制（与 Agent 参数进化互补）

---

*最后更新: 2026-04-14*