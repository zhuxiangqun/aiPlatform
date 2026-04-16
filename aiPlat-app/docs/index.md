# aiPlat-app 文档索引

## 概述

aiPlat-app 是 AI 中台的应用层（Layer 3），负责面向最终用户的应用实现。本层提供消息网关、CLI 工具、Web UI 等用户交互能力，是用户访问 AI 中台的入口。

**不是 API 层**：本层不提供 REST/GraphQL API，对外暴露的是用户直接使用的接口。

## 架构定位

### 层级关系

aiPlat-app 位于四层架构的第四层（Layer 3），是架构的最顶层：

- **向下依赖**：依赖 aiPlat-platform 的 REST/GraphQL API
- **被依赖方**：无（应用层是最终用户交互层）

### 职责边界

本层负责：

- 消息网关（渠道适配）
- CLI 工具
- Web UI 管理界面

本层不负责：

- 业务逻辑处理（由 aiPlat-core 提供）
- 认证授权（由 aiPlat-platform 提供）
- 数据存储（由 aiPlat-infra 提供）
- API 网关（由 aiPlat-platform 提供）

---

## 模块边界

### 对外暴露（用户直接使用）

| 类型 | 说明 |
|------|------|
| 消息网关 Webhook | Telegram/Slack/WebChat 回调端点 |
| WebSocket | 实时消息交互 |
| CLI 命令 | 命令行工具 |
| Web UI 页面 | 管理界面 |

### 向下依赖

- 只能依赖 `aiPlat-platform` 的 REST/GraphQL API
- **禁止直接依赖** `aiPlat-core` 或 `aiPlat-infra`

### 数据模型规则

- **可定义**：渠道数据模型（`TelegramMessage`、`SlackEvent`、`WebChatMessage`）
- **不可定义**：业务模型（`Agent`）、API 模型（`CreateAgentRequest`）、技术模型（`DatabaseConfig`）

## 核心模块

### channels - 消息通道

> 消息通道负责多渠道接入能力的统一抽象，支持 Telegram、Slack、WebChat 等。

**核心功能**：
- 渠道适配（Telegram/Slack/WebChat）
- 消息格式转换
- 协议转换
- 消息路由

**相关文档**：[channels 模块文档](./channels/index.md)

### events - 事件总线

> 事件总线是 AI Platform 应用层的消息通信中枢，提供发布-订阅模式的事件驱动机制。

**核心功能**：
- 事件发布订阅
- 队列管理
- 统计监控

**相关文档**：[events 模块文档](./events/index.md)

### cli - 命令行工具

命令行工具模块提供命令行界面，支持开发者通过命令行使用 AI 中台能力。

**核心概念**：

- **Command**：命令，执行特定功能的指令
- **Option**：选项，命令的参数配置
- **Argument**：参数，命令的位置参数
- **Context**：上下文，命令执行的环境信息

**命令类型**：

- **智能体命令**：创建、运行、管理智能体
- **技能命令**：注册、查询、执行技能
- **知识库命令**：创建、更新、检索知识库
- **工具命令**：注册、查询、调用工具
- **配置命令**：查看、设置、管理配置
- **诊断命令**：调试、测试、诊断问题

**主要能力**：

- 命令定义与解析
- 参数验证与转换
- 命令执行与输出
- 命令补全与帮助
- 配置文件管理
- 交互式输入

**设计原则**：

- 命令应该有清晰的命名
- 参数应该有默认值
- 输出应该是友好的
- 错误应该是可理解的

**相关文档**：[cli 模块文档](./cli/index.md)

### workbench - 工作台

工作台模块提供可视化的 Web 界面，是用户使用 AI 中台的主要入口。

**核心概念**：

- **Page**：页面，独立的用户界面
- **Component**：组件，可复用的界面元素
- **State**：状态，页面的数据状态
- **Action**：动作，用户的操作行为

**页面类型**：

- **仪表盘**：系统概览、使用统计、快捷入口
- **智能体管理**：智能体列表、创建、配置、运行
- **技能管理**：技能列表、注册、测试、执行
- **知识库管理**：知识库列表、创建、上传、检索
- **工具管理**：工具列表、注册、测试、调用
- **会话管理**：会话列表、历史记录、导出
- **系统设置**：配置管理、用户管理、权限管理

**主要能力**：

- 页面渲染与交互
- 状态管理与同步
- 表单验证与提交
- 数据展示与可视化
- 实时通信与更新
- 文件上传与下载

**设计原则**：

- 界面应该是直观的
- 交互应该是流畅的
- 响应应该是快速的
- 错误应该是友好的

**相关文档**：[workbench 模块文档](./workbench/index.md)

#### services - 应用服务（workbench 子模块）

> services 是 workbench 的子模块，负责前端与后端的 API 通信。

**核心概念**：

- **Service**：服务，封装特定领域的 API 调用
- **Client**：HTTP 客户端，处理请求拦截、响应转换

**服务类型**：

- **AgentService**：智能体服务，处理智能体相关 API
- **SkillService**：技能服务，处理技能相关 API
- **KnowledgeService**：知识库服务，处理知识库相关 API
- **ToolService**：工具服务，处理工具相关 API
- **SessionService**：会话服务，处理会话相关 API
- **AuthService**：认证服务，处理认证相关 API

**相关文档**：[services 模块文档](./services/index.md)

## 技术栈

### 前端技术

- **框架**：React，用于构建用户界面
- **状态管理**：Redux + Redux Toolkit，用于管理应用状态
- **路由**：React Router，用于页面导航
- **UI 组件库**：Tailwind CSS + 自定义组件，提供样式和组件
- **动画**：Framer Motion，用于交互动画
- **图标**：Lucide React，用于图标
- **HTTP 客户端**：Axios，用于 API 调用
- **构建工具**：Vite，用于项目构建
- **类型检查**：TypeScript，用于类型安全

### 命令行技术

- **框架**：Click，用于构建命令行工具
- **输出美化**：Rich，用于美化命令行输出
- **交互输入**：Questionary，用于交互式输入
- **配置管理**：Pydantic，用于配置验证

### 通信技术

- **HTTP**：RESTful API，用于同步请求
- **WebSocket**：实时通信，用于流式输出和实时更新
- **SSE**：Server-Sent Events，用于服务端推送

## 设计原则

### 依赖原则

- **单向依赖**：只依赖 aiPlat-platform，不直接访问 aiPlat-core 和 aiPlat-infra
- **接口隔离**：通过 API 与平台层交互，不直接访问内部实现
- **解耦设计**：前端与后端通过 API 解耦，支持独立开发和部署

### 设计原则

- **用户体验优先**：界面设计以用户体验为中心
- **响应式设计**：支持不同屏幕尺寸的适配
- **可访问性**：支持无障碍访问
- **国际化**：支持多语言

### 编码规范

- 使用 TypeScript，提高代码可维护性
- 使用组件化开发，提高代码复用性
- 使用状态管理，统一管理应用状态
- 使用单元测试，保证代码质量
- 使用端到端测试，保证功能正确性

## 按角色文档

- [架构师指南](./by-role/architect/index.md) - 架构设计、技术选型、模块划分
- [开发者指南](./by-role/developer/index.md) - 开发规范、组件使用、最佳实践
- [运维指南](./by-role/ops/index.md) - 部署配置、性能优化、故障排查
- [用户指南](./by-role/user/index.md) - 功能使用、操作指南、常见问题

### 各角色文档内容说明

| 角色 | 文档目录 | 包含内容 |
|------|----------|----------|
| 架构师 | [by-role/architect/](./by-role/architect/index.md) | 整体架构设计、模块依赖关系、核心抽象定义、技术选型依据、设计原则、扩展机制 |
| 开发者 | [by-role/developer/](./by-role/developer/index.md) | 开发环境搭建、核心模块使用、模块开发流程、最佳实践、测试指南、调试技巧 |
| 运维 | [by-role/ops/](./by-role/ops/index.md) | 部署配置说明、监控指标、告警规则、故障排查、备份恢复、安全管理 |
| 用户 | [by-role/user/](./by-role/user/index.md) | 核心概念、使用指南、最佳实践、常见问题 |

## 相关链接

- [主文档索引](../../docs/index.md) - 返回主文档
- [基础设施层文档](../../aiPlat-infra/docs/index.md) - aiPlat-infra 文档
- [核心层文档](../../aiPlat-core/docs/index.md) - aiPlat-core 文档
- [平台服务层文档](../../aiPlat-platform/docs/index.md) - aiPlat-platform 文档
