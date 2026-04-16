# aiPlatform - AI 中台系统

> 基于四层架构 + 独立管理系统的 AI 中台系统，提供清晰的责任划分和依赖管理

---

## 📖 一句话概述

aiPlatform 是一个企业级 AI 中台系统，采用四层架构 + 独立管理系统设计，提供清晰的依赖管理和模块化能力。

---

## 🏗️ 架构设计

### 业务系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                  aiPlat-app (Layer 3)                      │
│              应用层 - 面向用户的应用                          │
│   Message Gateway, CLI, Workbench, App Services            │
└────────────────────┬───────────────────────────────────────┘
                     │ 依赖
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-platform (Layer 2)                      │
│         平台服务层 - API、认证、多租户                        │
│   API, Auth, Tenants, API Gateway, Messaging, Registry     │
└────────────────────┬───────────────────────────────────────┘
                     │ 依赖
                     ↓
┌─────────────────────────────────────────────────────────────┐
│               aiPlat-core (Layer 1)                         │
│        AI 中台核心 - Agent、Skill、编排、知识                │
│  Core Runtime (Harness/Orchestration/Agents/Skills/Memory)  │
└────────────────────┬───────────────────────────────────────┘
                     │ 依赖
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-infra (Layer 0)                         │
│          基础设施层 - 数据库、日志、配置                      │
│     Database, Logging, Config, LLM, Vector, Monitoring     │
└─────────────────────────────────────────────────────────────┘
```

### 管理系统架构

```
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-management (Management System)          │
│          管理平面 - 监控、诊断、配置、告警                      │
└────────────┬─────────────────────────────────────────────────┘
             │ 管理接口
             ║
    ┌────────╨─────────┬─────────┬─────────┬────────────┐
    │                  │         │         │            │
    ▼                  ▼         ▼         ▼            ▼
┌────────┐       ┌────────┐ ┌────────┐ ┌────────┐
│ Layer 3│       │ Layer 2│ │ Layer 1│ │ Layer 0│
│  app   │       │platform│ │  core  │ │ infra  │
└────────┘       └────────┘ └────────┘ └────────┘
 管理 API         管理 API    管理 API   管理 API
```

**架构关系**：
- **业务系统**：`aiPlat-app → aiPlat-platform → aiPlat-core → aiPlat-infra`（单向依赖）
- **管理系统**：`aiPlat-management → 各层管理接口`（横切关系）

**核心原则**：
- ✅ 单向依赖
- ✅ 无循环依赖
- ✅ 下层完全独立
- ✅ 管理系统独立部署

---

## 🚀 快速开始

### 安装

安装所有层，或一次性安装整个系统。

### 基础使用

基础设施层提供数据库、LLM 客户端、向量数据库等基础服务。核心层提供 Core Runtime（Harness/Agent/Skill/编排）等 AI 能力。平台层提供 API、认证、多租户、API 网关等平台服务。应用层提供消息网关（多渠道接入）、CLI、Web UI 等用户界面。

### 运行服务

启动 API 服务（platform）、消息网关（app）或使用 CLI 工具进行管理。

---

## 📚 文档

### 系统文档

- **[详细文档](./docs/index.md)** - 架构设计、各层职责、使用指南

### 各层文档

| 层级 | 文档 | 核心模块 |
|------|------|---------|
| **Management** | [aiPlat-management](./aiPlat-management/docs/index.md) | Dashboard, Monitoring, Alerting |
| **Layer 3** | [aiPlat-app](./aiPlat-app/docs/index.md) | Message Gateway, CLI, Workbench |
| **Layer 2** | [aiPlat-platform](./aiPlat-platform/docs/index.md) | API, Auth, Tenants |
| **Layer 1** | [aiPlat-core](./aiPlat-core/docs/index.md) | Harness, Agents, Skills |
| **Layer 0** | [aiPlat-infra](./aiPlat-infra/docs/index.md) | Database, LLM, Vector |

---

## 🎯 各层职责

### Management: aiPlat-management（管理系统）

**职责**：独立的运维管理系统，横切四层业务架构

**核心模块**：
- `dashboard/` - 四层总览和健康状态聚合
- `monitoring/` - 指标采集和监控
- `alerting/` - 告警规则和通知
- `diagnostics/` - 健康检查和故障诊断
- `config/` - 配置管理和版本控制

**关键特点**：
- ✅ 独立于业务系统部署
- ✅ 业务层崩溃时仍可诊断
- ✅ 提供统一的运维管理视图

---

### Layer 0: aiPlat-infra（基础设施层）

**职责**：提供最底层的基础设施能力，完全独立

**核心模块**：
- `database/` - 数据库抽象（PostgreSQL/MySQL/MongoDB）
- `llm/` - LLM 客户端（OpenAI/Anthropic/DeepSeek）
- `vector/` - 向量数据库（FAISS/Milvus/Pinecone）
- `config/` - 配置管理（多环境/多源）
- `logging/` - 结构化日志
- `monitoring/` - 系统监控
- `observability/` - 可观测性
- `di/` - 依赖注入容器

---

### Layer 1: aiPlat-core（AI 中台核心）

**职责**：封装 AI 核心能力和业务逻辑

**核心模块**：
- `harness/` - Harness 执行引擎（8大要素）
- `orchestration/` - 编排引擎（LangGraph 工作流）
- `agents/` - Agent 实现
- `skills/` - Skill 实现
- `tools/` - 工具系统
- `memory/` - 记忆系统
- `knowledge/` - 知识系统
- `services/` - 业务服务

---

### Layer 2: aiPlat-platform（平台服务层）

**职责**：对外暴露 API，提供平台级服务

**核心模块**：
- `api/` - REST/GraphQL API
- `auth/` - 认证授权（OAuth2/JWT/RBAC）
- `tenants/` - 多租户管理
- `gateway/` - API Gateway
- `registry/` - 能力注册表
- `billing/` - 计费系统
- `governance/` - 治理（限流/审计）

---

### Layer 3: aiPlat-app（应用层）

**职责**：面向用户的应用

**核心模块**：
- `gateway/` - 消息网关（Message Gateway，多渠道接入）
- `cli/` - CLI 工具
- `workbench/` - Web UI（React/Vue）
- `services/` - 应用服务（PlatformClient SDK）

---

## ⚙️ 开发规范

### 依赖管理

**严禁**：
- ❌ app 直接导入 core
- ❌ app 直接导入 infra
- ❌ platform 直接导入 infra
- ❌ 任何下层导入上层

**必须是**：
- ✅ app 只导入 platform
- ✅ platform 只导入 core
- ✅ core 只导入 infra
- ✅ infra 不导入任何内部模块

### 命名规范

- **模块名**：小写下划线，如 `agent_registry.py`
- **类名**：大骆驼，如 `AgentRegistry`
- **函数名**：小写下划线，如 `get_agent()`
- **常量**：全大写，如 `MAX_RETRIES`

---

## 🛠️ 技术栈

| 层级 | 技术栈 |
|------|--------|
| **management** | FastAPI, Prometheus, InfluxDB, Jaeger, React |
| **infra** | PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ, FAISS, Milvus |
| **core** | LangGraph, LangChain, Anthropic API, OpenAI API |
| **platform** | FastAPI, OAuth2, JWT, Prometheus, Grafana |
| **app** | React, Vue, Click, WebSocket |

---

## 📄 许可证

MIT License

---

## 👥 维护者

aiPlatform Team
