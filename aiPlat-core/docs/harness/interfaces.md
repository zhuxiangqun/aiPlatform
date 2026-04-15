# 接口定义 (Interfaces)

> Harness 操作系统层的接口定义，统一规范各模块的实现。

---

## 一句话定义

**接口定义是 Harness 的契约层**——通过统一接口规范，确保各模块可替换、可扩展。

---

## 核心接口

### 1. IAgent - 智能体接口

**智能体接口**

定义智能体的核心契约：

- **执行**：接收上下文，返回执行结果
- **初始化**：根据配置初始化智能体实例
- **清理**：释放智能体占用的资源

**配置对象**：

- 名称、模型、温度参数、最大 Token 数

**结果对象**：

- 成功标志、输出内容、错误信息、元数据

### 2. ITool - 工具接口

**工具接口**

定义工具的核心契约：

- **执行**：接收参数，返回执行结果
- **参数验证**：验证输入参数的合法性

**配置对象**：

- 名称、描述、参数定义、超时时间

**结果对象**：

- 成功标志、输出内容、错误信息

### 3. ISkill - 技能接口

**技能接口**

定义技能的核心契约：

- **执行**：接收上下文和参数，返回执行结果
- **验证**：验证输入参数的合法性

**配置对象**：

- 名称、描述、输入模式、输出模式

**结果对象**：

- 成功标志、输出内容、错误信息

### 4. ILoop - 执行循环接口

**执行循环接口**

定义执行循环的核心契约：

- **运行**：执行完整的循环流程
- **继续判断**：根据当前状态判断是否继续

**循环状态**：

- 初始、推理中、行动中、观察中、已完成、错误

**状态对象**：

- 当前状态、步骤计数、已用 Token、总预算、上下文

### 5. ICoordinator - 协调器接口

**协调器接口**

定义多 Agent 协调的核心契约：

- **协调**：协调多个智能体完成任务
- **收敛检测**：检测多 Agent 结果是否收敛

### 6. IContext - 上下文接口

**上下文接口**

定义上下文的存储和访问契约：

- **获取**：根据键获取存储的值
- **设置**：存储键值对
- **清空**：清空所有上下文数据

### 7. IRouter - 路由接口

**路由接口**

定义请求路由的核心契约：

- **路由**：根据请求内容路由到目标
- **注册**：注册新的路由目标

### 8. IAdapter - 适配器接口

**适配器接口**

定义数据适配的核心契约：

- **元数据**：获取适配器名称、版本、能力
- **适配**：将数据转换为目标格式
- **恢复**：将适配后的数据恢复为原格式

---

## 接口目录结构

```
harness/interfaces/
├── __init__.py
├── agent.py                        # IAgent, AgentConfig, AgentResult
├── tool.py                         # ITool, ToolConfig, ToolResult
├── skill.py                        # ISkill, SkillConfig, SkillResult
├── loop.py                         # ILoop, LoopState, LoopResult
├── coordinator.py                  # ICoordinator, CoordinationResult
├── context.py                      # IContext, ContextData
├── router.py                       # IRouter, RouteTarget
└── adapter.py                      # IAdapter, AdapterMetadata
```

---

## 接口设计原则

| 原则 | 说明 |
|------|------|
| **最小接口** | 接口方法尽可能少，只暴露必要能力 |
| **依赖倒置** | 高层模块依赖抽象，不依赖具体实现 |
| **接口隔离** | 使用专用接口，不使用庞大通用接口 |
| **开闭原则** | 对扩展开放，对修改封闭 |

---

## 与实现的关系

| 接口 | 实现位置 |
|------|----------|
| IAgent | `apps/agents/` |
| ITool | `apps/tools/` |
| ISkill | `apps/skills/` |
| ILoop | `harness/execution/` |
| ICoordinator | `harness/coordination/` |
| IContext | `harness/memory/` |
| IRouter | `harness/coordination/` |
| IAdapter | `adapters/` |

---

## 相关文档

- [Harness 索引](./index.md) - Harness 完整定义
- [执行系统](./execution.md) - 执行循环
- [适配器文档](../adapters/llm.md) - LLM 适配器

---

*最后更新: 2026-04-14*