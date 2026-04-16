# 运行时接入模块（App Layer 3）

> **重要说明（边界澄清）**  
> AI Platform 的**核心执行引擎（Core Runtime）**属于 **aiPlat-core（Layer 1）**（Harness / 编排 / Agents / Skills / Memory / Knowledge 等）。  
> 本文档描述的是 **aiPlat-app（Layer 3）** 在消息网关/CLI/Web UI 场景下的**运行时接入与会话编排**：包括会话管理、输入输出编排、调用 platform API、以及流式输出/重试等工程能力。  
>
> 如需了解真正的执行引擎实现与设计，请优先阅读：
> - [aiPlat-core Harness 文档](../../../aiPlat-core/docs/harness/index.md)
> - [aiPlat-core Agents 文档](../../../aiPlat-core/docs/agents/index.md)
> - [系统架构索引](../../../docs/index.md)

---

## 一、模块定位（接入层）

### 1.1 核心职责

运行时接入模块在整个 AI Platform 架构中承担以下职责：

| 职责 | 说明 |
|------|------|
| **会话编排** | 维护 app 层会话状态，组织输入/输出与上下文透传 |
| **平台调用** | 通过 platform 的 REST/GraphQL API 触发 Agent/Skill 等核心能力 |
| **流式输出/交互** | 支持 WebSocket/SSE/CLI 交互式输出等 |
| **可靠性增强** | 重试、超时、降级、幂等等工程能力（不包含核心业务逻辑） |

> 注意：如遇到与“执行引擎 / Runtime”相关的概念口径，请以 **aiPlat-core 的 Core Runtime** 为准；本层仅保留“接入与编排”的视角。

### 1.2 与相邻模块的关系

```
外部渠道/用户
  │
  ├─► Message Gateway（Layer 3, app）
  │     - 渠道适配 / 协议转换 / 消息格式统一
  │
  ├─► CLI / Web UI（Layer 3, app）
  │     - 参数解析 / 交互式输入 / 前端展示
  │
  └─► Platform API（Layer 2, platform）
        - Auth / Tenants / API Gateway / Governance
        - 对外契约（REST/GraphQL）
              │
              ▼
        Core Runtime（Layer 1, core）
        - Harness / Orchestration / Agents / Skills / Memory / Knowledge
```

---

## 二、接入层接口与契约（App）

> 本层**不定义** Core Runtime 的执行模型/内部状态机等概念；这些属于 **aiPlat-core**。  
> app 层以 **platform API** 的请求/响应模型为准（即：platform 对外契约）。

### 2.1 典型调用：触发 Agent 执行

**调用链**：app → platform → core  

```python
# 伪代码：app 内通过 platform 客户端调用

execution = await platform_api.execute_agent(
    agent_id="agent-xxx",
    input={"message": "hello"},
    context={
        "user_id": "u-1",
        "session_id": "s-1",
        "channel": "telegram",
    },
)
```

推荐做法：
- 将 `user_id/session_id/channel` 作为 context 透传（便于平台鉴权、审计、追踪）
- 将 trace/execution id 作为“可观测性跳转入口”（Links/Traces/Graphs）

### 2.2 会话与上下文编排

app 层主要负责：
- 把外部渠道/CLI/Web UI 的输入规范化为统一的 `input + context`
- 维护“用户会话”视角（例如 session_id 的生成与绑定）
- 对接流式输出（SSE/WebSocket）与失败重试策略

### 2.3 流式输出（SSE/WebSocket）

建议约定：
- **SSE**：适合 Web UI 的流式 token 输出
- **WebSocket**：适合双向交互（中断/续写/工具执行过程展示）

---

## 三、历史对照（附录）

本章节用于迁移期对照，不代表当前实现归属：
- “Core Runtime（执行引擎）”相关能力属于 **aiPlat-core**
- app 层仅保留“接入编排”与“用户交互”的工程侧能力

---

## 四、相关文档

- [系统架构索引](../../../docs/index.md)
- [平台层文档索引（对外契约）](../../../aiPlat-platform/docs/index.md)
- [核心层：Harness](../../../aiPlat-core/docs/harness/index.md)
- [核心层：Agents](../../../aiPlat-core/docs/agents/index.md)
- [channels 通道适配器文档](../channels/index.md)
- [events 事件总线文档](../events/index.md)
- [workbench 文档](../workbench/index.md)
- [management 管理平面 - App](../../../aiPlat-management/docs/app/index.md)
- [aiPlat-infra memory 模块](../../../aiPlat-infra/docs/memory/index.md)
- [aiPlat-infra llm 模块](../../../aiPlat-infra/docs/llm/index.md)
