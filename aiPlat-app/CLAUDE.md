---
purpose: aiPlat-app 项目级 AI 编程规约
scope: app (Layer 3)
language: zh-CN
---

# aiPlat-app AI 编程规约（应用层）

本文件用于约束 AI Agent 在 aiPlat-app 仓库内的行为。

---

## 0. 优先级（从高到低）
1. 正确性与可验证性（构建/测试通过）
2. 最小改动面（Surgical Changes）
3. 简单性（Simplicity First）
4. 一致性（UI 规范、渠道适配模式、CLI 命令风格）

---

## 1) Think Before Coding：不确定先问
- 涉及新增渠道（Telegram/Slack/WebChat 等）
- 涉及 UI 交互设计（组件、页面、路由）
- 涉及 CLI 命令设计（命令命名、参数、输出格式）
- 涉及跨层调用（禁止直接访问 core/infra）

### 1.1 代码优先于设计文档（强制）
设计文档（`docs/`）描述目标状态，代码才是当前真实状态。两者冲突时以代码为准，设计文档标注"已过期/已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止仅凭记忆或上次审计的印象做判断，每次结论必须附带代码搜索证据（命中文件路径+行号）。

---

## 2) Simplicity First：最小实现
- 新增渠道复用已有适配器模式（ChannelAdapter 接口）
- UI 组件优先复用现有组件库，不引入新依赖
- CLI 命令遵循现有命名和输出规范

---

## 3) Surgical Changes：手术式改动
- 只修改与需求直接相关的文件
- 不改无关的渠道适配、UI 组件、CLI 命令
- 前端改 UI 时不同时动后端 API 层

---

## 4) Goal-Driven Execution：验收闭环
- 前端：`npm run build`（或等效构建命令）
- CLI：`python -m py_compile` + 执行命令验证
- 渠道：模拟消息验证适配正确性

---

## 5) 项目特定：app 层边界与设计模式（必须遵守）

### 5.1 层定位（来自 `docs/index.md` 和 `../../docs/index.md`）

aiPlat-app 是 **Layer 3（应用层）**，面向最终用户，**不是 API 层**。

- **对外暴露**：消息网关 Webhook、CLI 命令、Web 页面
- **向下依赖**：只能依赖 `aiPlat-platform` 的 REST/GraphQL API
- **禁止直接依赖** `aiPlat-core` 或 `aiPlat-infra`
- **不覆盖**：Agent 执行逻辑（core）、API 定义（platform）、数据库操作（infra）

### 5.2 数据模型规则

app 层只拥有渠道相关数据模型（如 `TelegramMessage`、`SlackEvent`、`WebChatMessage`）。禁止在 app 层定义业务模型（Agent、Skill 等）、API 模型（CreateAgentRequest 等）、技术模型（DatabaseConfig 等）。

### 5.3 消息网关 = 渠道适配 + 格式转换 + 协议转换

消息网关的职责仅限于：
- 接收外部渠道的 Webhook 回调
- 将渠道消息格式转换为统一的内部格式
- 转发到 platform 的 REST API
- 不涉及任何 AI 业务逻辑

### 5.4 依赖方向

```
app → platform (通过 REST/GraphQL API，唯一入口)
app → core (禁止，应通过 platform)
app → infra (禁止，应通过 platform)
```

### 5.5 前端 UI 配置驱动原则（延展自 core 设计原则）

UI 组件对流水线状态的判断不应依赖硬编码的 artifact key 名称（如 `key === 'test_report'`）。需特殊处理时，依据 artifact 的**结构特征**（如有没有 `recommendation` 字段），而非 key 的名称。

**设计文档依据**：
- `../../docs/index.md` §设计原则、§Layer 3 边界规则、§依赖规则
- `../../docs/architecture/system-architecture-contract.md` §依赖方向
- `../../aiPlat-core/CLAUDE.md` §5.4 配置驱动原则

---

## 6) 输出要求
- 改动摘要（改了哪些文件，为什么）
- 验证结果（构建/测试是否通过）
- 涉及用户交互时：说明 UI 行为变化
