# aiPlatform 文档索引

> AI 中台系统 - 四层架构 + 独立管理系统

---

### 按角色

| 角色 | 文档目录 | 说明 |
|------|---------|------|
| 架构师 | [架构师指南](by-role/architect/index.md) | 架构设计、依赖管理、ADR 记录 |
| 开发者 | [开发者指南](by-role/developer/index.md) | 开发指南、最佳实践、测试指南 |
| 运维 | [运维指南](by-role/ops/index.md) | 部署运维、监控配置、故障排查 |
| 用户 | [用户指南](by-role/user/index.md) | 使用指南、API 文档、常见问题 |

> **说明**：主文档提供系统级设计概览（架构、设计原则、层间契约）；角色文档提供角色视角的详细操作指南。两者互补，不重复。

---

### 各角色文档内容说明

| 角色 | 文档目录 | 包含内容 |
|------|----------|----------|
| 架构师 | [by-role/architect/](by-role/architect/index.md) | 架构设计理念、技术选型依据、模块划分原则、依赖关系管理、扩展机制设计 |
| 开发者 | [by-role/developer/](by-role/developer/index.md) | 开发环境搭建、模块开发流程、核心模块使用、最佳实践、测试指南、调试技巧 |
| 运维 | [by-role/ops/](by-role/ops/index.md) | 部署拓扑、配置参数说明、监控指标、告警规则、故障排查、备份恢复、安全管理 |
| 用户 | [by-role/user/](by-role/user/index.md) | 快速开始、核心概念、使用指南、最佳实践、常见问题 |

---

### 系统文档

| 系统 | 文档 | 核心模块 | 说明 |
|------|------|---------|------|
| **Management** | [aiPlat-management](../aiPlat-management/docs/index.md) | Dashboard, Monitoring, Alerting | 独立的运维管理系统 |

---

### 各层文档

| 层级 | 文档 | 核心模块 | 测试状态 |
|------|------|---------|---------|
| **Layer 3** | [aiPlat-app](../aiPlat-app/docs/index.md) | Message Gateway, CLI, Workbench | - |
| **Layer 2** | [aiPlat-platform](../aiPlat-platform/docs/index.md) | API, Auth, Tenants, Billing | - |
| **Layer 1** | [aiPlat-core](../aiPlat-core/docs/index.md) | Harness, Agents, Skills, Memory | - |
| **Layer 0** | [aiPlat-infra](../aiPlat-infra/docs/index.md) | Database, LLM, Vector, Config | ✅ [测试文档](../aiPlat-infra/docs/testing/index.md) |

> **测试状态**：aiPlat-infra层已完成100%测试覆盖，包括单元测试和集成测试。详见[测试文档索引](../aiPlat-infra/docs/testing/index.md)。

---

## 设计规范

- [系统级 UI 设计规范](UI_DESIGN.md) - 统一整个系统的前端设计语言和编程标准
- [UI 实现状态](UI_IMPLEMENTATION_STATUS.md) - 记录 As‑Is/进度/差异，避免污染设计规范
- [系统级测试指南](TESTING_GUIDE.md) - 测试策略、分层测试方法、跨层测试规范

### 功能增强设计

| 方向 | 设计文档 | 状态 | 说明 |
|------|----------|------|------|
| MCP 协议集成 | [mcp/index.md](mcp/index.md) | ✅ | 连接外部 MCP 服务器 |
| 工具系统增强 | [tools/enhancement.md](tools/enhancement.md) | ✅ | HTTP/Browser/Database/Code 工具 + Hook 机制（含内置 Hook） |
| 反馈闭环增强 | [harness/feedback-gates.md](harness/feedback-gates.md) | ✅ | 质量门禁、安全扫描 + Agent 评估体系 |
| 渐进式披露机制 | [harness/progressive-disclosure.md](harness/progressive-disclosure.md) | ✅ | 按需加载上下文 + 多层记忆 |
| 多层记忆架构 | [harness/memory.md](harness/memory.md) | ✅ | Working/Episodic/Semantic 三层记忆 |
| Subagent 架构 | [agents/subagent.md](agents/subagent.md) | ✅ | 派生子 Agent、权限隔离、协调调度 |
| Skill 动态进化 | [skills/evolution.md](skills/evolution.md) | ✅ | 自动捕获、修复、衍生 |
| Skill 文件格式 | [aiPlat-core 技能文件格式](../aiPlat-core/docs/skills/file-format.md) | ✅ | OpenClaw 兼容、trigger_keywords、Category 分类、Script 执行器 |

**各层测试指南**：
| 层级 | 测试指南 | 状态 |
|------|----------|------|
| Layer 0 (infra) | [测试指南](../aiPlat-infra/docs/testing/index.md) | ✅ 已完成 |
| Layer 1 (core) | 待补充 | 🚧 进行中 |
| Layer 2 (platform) | 待补充 | 📝 计划中 |
| Layer 3 (app) | 待补充 | 📝 计划中 |

---

## 架构设计

### 架构概览

#### 核心能力层（Layer 1）执行体系

- [核心能力层（Layer 1）最新架构图与执行流程](architecture/core-layer1-latest.md)

```
┌─────────────────────────────────────────────────────────────┐
│                  aiPlat-app (Layer 3)                      │
│   应用层 - Message Gateway, CLI, Workbench, App Services   │
│                  [文档](../aiPlat-app/docs/index.md)        │
└────────────────────┬───────────────────────────────────────┘
                       │ 依赖
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-platform (Layer 2)                      │
│   平台服务层 - API, Auth, Tenants, API Gateway, Billing     │
│                [文档](../aiPlat-platform/docs/index.md)      │
└────────────────────┬───────────────────────────────────────┘
                       │ 依赖
                       ↓
┌─────────────────────────────────────────────────────────────┐
│               aiPlat-core (Layer 1)                         │
│ AI 中台核心 - Core Runtime (Harness/Orchestration/Agents)  │
│                  [文档](../aiPlat-core/docs/index.md)        │
└────────────────────┬───────────────────────────────────────┘
                       │ 依赖
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-infra (Layer 0)                         │
│      基础设施层 - Database, LLM, Vector, Monitoring         │
│                  [文档](../aiPlat-infra/docs/index.md)       │
└─────────────────────────────────────────────────────────────┘
```

**依赖方向**：
```
aiPlat-app → aiPlat-platform → aiPlat-core → aiPlat-infra

单向依赖
无循环依赖
下层完全独立
```

> **图例说明**：架构概览图展示的是**静态依赖关系**（编译时/设计时的模块依赖），网关调用链图展示的是**运行时调用链**（请求处理流程）。

---

### 网关调用链

```
外部渠道 → Layer 3 消息网关 → Layer 2 API 网关 → Layer 1 核心服务

┌──────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ 外部渠道     │                    │              │                    │              │
│ - Telegram   │  ────────────────> │  消息网关    │  ────────────────> │  API 网关    │
│ - Slack      │                    │  (Layer 3)   │                    │  (Layer 2)   │
│ - WebChat    │                    │              │                    │              │
└──────────────┘                    └──────────────┘                    └──────────────┘
                                           │                                    │
                                           │ 渠道适配                           │ 认证、限流
                                           │ 消息格式转换                       │ 路由、熔断
                                           │ 协议转换                          │ 负载均衡
                                           └───────────────────────────────────────┘
```

**职责划分**：

| 网关 | 层级 | 职责 |
|------|------|------|
| 消息网关 | Layer 3 (app) | 渠道适配、消息格式转换、协议转换 |
| API 网关 | Layer 2 (platform) | 认证授权、限流熔断、路由分发、负载均衡 |

**调用关系**：
- 消息网关收到外部消息后，统一转发到 API 网关
- API 网关完成认证、限流等处理后，路由到对应的 Core 服务
- 所有安全策略（认证、限流）统一在 API 网关实施

---

### 设计原则

> **说明**：设计原则回答「是什么」的问题，定义系统应该遵循的基本规则；架构决策回答「为什么」的问题，记录实际选择特定方案的理由和考量。

#### 1. 单向依赖原则

**严格规则**：
- 上层可以依赖下层，下层不能依赖上层
- app → platform → core → infra
- 各层只能通过公开接口访问，不能跨层调用

**禁止的依赖**：
- app 直接访问 core（应通过 platform）
- app 直接访问 infra（应通过 platform）
- platform 直接访问 infra（应通过 core）

> 详细的依赖检查工具和 CI 行为请参考「跨层调用约束 → 依赖检查落地」章节。

**模块边界**：

| 层 | 对外入口 | 其他模块不可直接导入 |
|----|----------|---------------------|
| infra | `aiPlat_infra.factories` | 具体实现类 |
| core | `aiPlat_core.facades.CoreFacade` | Agent、Skill 具体类 |
| platform | REST API、GraphQL API | 内部服务类 |
| app | 无（不是 API 层） | 无 |

---

#### 2. 接口隔离原则

每一层通过接口抽象，不依赖具体实现。

**基础设施层接口**：
- 数据库接口提供统一的查询和事务方法
- LLM 客户端接口提供统一的对话和嵌入方法
- 向量存储接口提供统一的搜索和管理方法

**核心层接口**：
- Agent 接口定义统一的执行方法
- Skill 接口定义统一的技能执行方法
- 编排器接口定义统一的工作流编排方法

**平台层接口**：
- 通过门面模式提供统一的能力访问接口
- 通过依赖注入管理服务实例
- 通过配置驱动初始化各个组件

---

#### 3. 依赖注入原则

使用 DI 容器管理所有服务依赖。

**依赖注入容器**：
- 基础设施层注册数据库、LLM、向量存储等基础服务
- 核心层注册 Agent、Skill、编排器等核心服务
- 平台层注册 API、认证、多租户等平台服务
- 应用层通过容器获取所需服务

**配置管理**：
- 所有服务通过配置文件初始化
- 支持多环境配置（开发、测试、生产）
- 支持环境变量覆盖配置
- 配置源支持文件、环境变量、远程配置中心

---

#### 4. 配置驱动原则

所有模块通过配置初始化，不硬编码任何参数。

**配置层次**：
- 基础配置：数据库连接、LLM API 密钥、向量存储配置
- 核心配置：Agent 参数、Skill 参数、编排策略
- 平台配置：API 端口、认证方式、限流规则
- 应用配置：Gateway 配置、CLI 命令、UI 配置

**配置优先级**：
- 环境变量优先于配置文件
- 远程配置优先于本地配置
- 支持动态配置更新

**配置项类别**：

| 类别 | 说明 | 示例 |
|------|------|------|
| 环境标识 | 运行环境 | `dev`, `staging`, `prod` |
| 连接信息 | 外部服务地址 | 数据库 DSN、Redis 地址 |
| 认证凭证 | API 密钥（通过密钥管理） | LLM API Key、数据库密码 |
| 运行时参数 | 行为调优 | Agent 超时、重试次数 |
| 功能开关 | 特性启用/禁用 | 实验性功能、维护模式 |

**配置来源优先级**（高到低）：
1. 环境变量
2. 密钥管理服务（Vault / K8s Secrets）
3. 配置文件
4. 默认值

---

### 关键架构决策

| 决策 | 理由 | 替代方案 | 为什么选这个 |
|------|------|----------|--------------|
| 四层架构 | 职责清晰，依赖可控 | 微服务、两层架构 | 团队规模 5-15 人，单体+分层更高效，减少分布式复杂度 |
| platform 不直接访问 infra | 保持 infra 可替换性 | platform 直接访问数据库/LLM | 如果 platform 直接访问 infra，切换数据库/LLM 时需要修改上层代码 |
| core 提供门面而非直接暴露 | 隔离内部重构影响 | 直接暴露 Agent/Skill 类 | 门面可以独立演进，内部实现变更不影响上层调用方 |
| 配置驱动 | 支持多环境、动态切换 | 参数硬编码 | 适配云原生部署、多 LLM 提供商、多环境部署 |
| 消息网关+API 网关双网关 | 职责分离，安全统一 | 单一网关处理所有 | 消息网关专注渠道适配，API 网关专注安全治理，职责分离更清晰 |

---

## 跨层调用约束

### 各层职责边界

---

#### Layer 0: aiPlat-infra（基础设施层）

**定位**：管理和抽象所有基础设施资源，包括**硬件资源**（计算、内存、存储、网络）和**软件服务**（数据库、LLM、向量存储、消息队列、可观测性）。本层完全独立，不依赖任何内部模块。

**覆盖范围**：

> **说明**：infra 层提供统一的资源管理抽象，底层实现可以是 Kubernetes API（推荐生产环境）、Docker API（开发测试）、或裸机管理（特殊场景）。

**1. 硬件资源管理**
| 资源类型 | 覆盖内容 | 管理职责 |
|----------|----------|----------|
| 计算资源 | CPU、GPU、NPU、TPU | 资源分配、任务调度、弹性扩缩、负载均衡、算力配额 |
| 内存资源 | RAM、VRAM（显存）、HBM | 多级缓存（L1/L2/L3）、内存池、显存管理、OOM 防护、内存回收 |
| 存储资源 | 本地磁盘（SSD/NVMe）、网络存储（S3/NFS/Ceph/OSS） | 文件读写、块存储、对象存储、生命周期管理、TTL 清理、备份归档 |
| 网络资源 | 服务网络、数据网络、管理网络 | 服务发现（Consul/etcd）、负载均衡（Nginx/Envoy）、网络策略（NetworkPolicy）、流量控制、DNS 管理 |

**2. 软件服务抽象**
| 服务类型 | 覆盖内容 | 管理职责 |
|----------|----------|----------|
| 关系型数据库 | PostgreSQL、MySQL、MariaDB、SQL Server | 连接池、事务管理、查询优化、读写分离、主从复制、分库分表 |
| 非关系型数据库 | MongoDB、Cassandra、Redis | 文档存储、键值存储、列存储、缓存管理 |
| LLM 服务 | OpenAI、Anthropic、DeepSeek、Google Gemini、本地模型（vLLM/TGI） | 推理引擎、模型加载、模型量化、推测解码、成本追踪、模型监控 |
| 向量存储 | Milvus、FAISS、Pinecone、Qdrant、Weaviate | 向量索引（HNSW/IVF/Flat）、相似度搜索（欧氏/余弦/内积）、索引优化、分片管理 |
| 消息队列 | Kafka、RabbitMQ、Redis Streams、Pulsar、AWS SQS | 消息生产消费、队列管理、死信处理、顺序保证、至少一次/恰好一次语义 |
| HTTP 客户端 | - | HTTP 请求重试（指数退避）、超时控制、连接池管理 |

**不覆盖的内容**：
| 不覆盖 | 说明 | 归属层 |
|--------|------|--------|
| Agent 业务逻辑 | Agent 定义、注册、执行、编排 | core |
| Skill 业务逻辑 | Skill 定义、触发条件、执行流程 | core |
| 业务数据模型 | Agent、Skill、Session、Message、Knowledge、Tool 等 | core |
| API 定义 | REST 路由、GraphQL schema、WebSocket 端点 | platform |
| API 网关逻辑 | 限流、熔断、路由、认证 | platform |
| 认证授权逻辑 | OAuth2、JWT、RBAC、权限模型 | platform |
| 渠道适配 | Telegram、Slack、WebChat 消息处理 | app |
| 用户界面 | Web UI、CLI 交互、命令行解析 | app |

**边界规则**：
- **向上提供**：工厂接口（`create_database_client()`、`create_llm_client()` 等）、配置加载接口（`load_config()`）、公共数据类型
- **向下依赖**：不依赖任何内部模块
- **禁止暴露**：具体实现类（如 `PostgresClient`）、内部工具类、第三方 SDK 细节

---

#### Layer 1: aiPlat-core（AI 中台核心层）

**定位**：封装 AI 核心能力和业务逻辑，是系统的业务中枢。本层不关心如何暴露（HTTP/CLI）也不关心如何存储（数据库/文件）。

**覆盖范围**：

**1. Agent 管理** - Agent 定义、注册、执行、生命周期管理
**2. Skill 管理** - Skill 定义、注册、执行
**3. 编排引擎** - 工作流定义、执行、多 Agent 协调
**4. 记忆系统** - 短期记忆、长期记忆、工作记忆
**5. 知识系统** - RAG 检索、知识图谱、文档处理
**6. 工具系统** - 工具定义、注册、执行
**7. 提示词管理** - 模板管理、版本管理、A/B 测试

**不覆盖的内容**：
| 不覆盖 | 说明 | 归属层 |
|--------|------|--------|
| 数据库 SQL | 具体数据库操作 | infra |
| LLM API 调用细节 | HTTP 请求、重试、超时 | infra |
| 向量存储操作 | 向量索引的具体实现 | infra |
| HTTP 路由定义 | REST API 端点 | platform |
| 认证逻辑 | Token 生成、验证 | platform |
| 渠道适配 | Telegram/Slack 消息解析 | app |

**边界规则**：
- **向上提供**：CoreFacade（唯一对外入口）、注册表接口
- **向下依赖**：依赖 infra 层的工厂接口
- **禁止暴露**：具体 Agent 实现类、内部编排逻辑

---

#### Layer 2: aiPlat-platform（平台服务层）

**定位**：对外暴露 API，提供平台级服务，是系统的对外门户。本层不包含 AI 核心逻辑，只做请求路由、协议转换、安全治理。

**覆盖范围**：

**1. API 服务** - REST API、GraphQL API、WebSocket API
**2. 认证授权** - OAuth2、OIDC、JWT、RBAC、用户管理
**3. 多租户管理** - 租户注册、数据隔离、配额管理
**4. 计费系统** - 使用量计量、成本计算、账单管理
**5. 治理** - 审计、合规检查

**不覆盖的内容**：
| 不覆盖 | 说明 | 归属层 |
|--------|------|--------|
| Agent 执行逻辑 | Agent 的具体执行流程 | core |
| 数据库 SQL | 具体数据库操作 | infra |
| 渠道适配 | Telegram/Slack 消息解析 | app |
| 用户界面 | Web UI、CLI 交互 | app |

**边界规则**：
- **向上提供**：REST API、GraphQL API、WebSocket API、Python/JS SDK
- **向下依赖**：依赖 core 层的 CoreFacade（唯一入口），**禁止直接依赖 infra 层**
- **禁止暴露**：内部服务类、数据库模型、core 层调用细节

---

#### Layer 3: aiPlat-app（应用层）

**定位**：面向用户的最终应用（消息网关、CLI、Web UI）。本层是系统的用户触点，**不是 API 层**。

**覆盖范围**：

**1. 用户应用**
- **消息网关** - 渠道适配、消息格式转换、协议转换
- **CLI 工具** - Agent 管理、Skill 管理、知识库管理
- **Web UI** - Agent 管理、Skill 管理、知识库管理、监控仪表盘

**不覆盖的内容**：
| 不覆盖 | 说明 | 归属层 |
|--------|------|--------|
| Agent 执行逻辑 | Agent 的具体执行流程 | core |
| API 定义 | REST 路由、GraphQL schema | platform |
| 数据库操作 | SQL 查询 | infra |

**边界规则**：
- **向上提供**：无（app 层不是 API 层）
- **对外暴露**：消息网关 Webhook、CLI 命令、Web 页面
- **向下依赖**：依赖 platform 层的 REST/GraphQL API（唯一入口），**禁止直接依赖 core 层或 infra 层**
- **禁止暴露**：内部适配器、platform 层调用细节

---

### 依赖规则

**允许的依赖**：
```
app → platform (通过 REST/GraphQL API)
platform → core (通过 CoreFacade)
core → infra (通过工厂接口)
```

**禁止的跨层依赖**：
```
app → core (禁止，应通过 platform)
app → infra (禁止，应通过 platform)
platform → infra (禁止，应通过 core)
```

---

### 依赖检查落地

**检查工具**：
- **import-linter**：检查跨层导入规则
- **dependency-cruiser**：检查模块边界和循环依赖

**CI 行为**：
- PR 提交时自动运行依赖检查
- 检查不通过 → 阻止合并
- 特殊情况需架构师审批豁免

---

### 四层边界对照总表

| 维度 | Layer 0 (infra) | Layer 1 (core) | Layer 2 (platform) | Layer 3 (app) |
|------|-----------------|----------------|---------------------|---------------|
| **定位** | 基础设施抽象 | AI 核心能力 | API 与平台服务 | 用户应用 |
| **覆盖** | 硬件资源、软件服务、可观测性 | Agent、Skill、编排、记忆、知识、工具 | API、认证、多租户、网关、计费 | 消息网关、CLI、Web UI |
| **向上提供** | 工厂接口、配置接口 | CoreFacade | REST/GraphQL API | 无（不是 API 层） |
| **向下依赖** | 无 | infra 工厂接口 | core CoreFacade | platform REST API |
| **禁止依赖** | - | - | infra | core、infra |
| **数据模型** | 技术模型 | 业务模型 | API 模型 | 渠道模型 |

---

## 版本兼容性

### 层间契约

| 依赖关系 | 契约形式 | 变更影响 |
|----------|----------|----------|
| app → platform | REST/GraphQL API | API 变更需版本升级 |
| platform → core | CoreFacade 接口 | 接口变更需版本升级 |
| core → infra | 工厂接口 | 新增实现不影响上层 |

### 版本策略

- **主版本号（MAJOR）**：不兼容的接口变更
- **次版本号（MINOR）**：新增功能，向下兼容
- **补丁版本（PATCH）**：bug 修复，完全兼容

---

## 快速开始

### 新手入门路径

**学习顺序**：
1. 阅读项目总览，了解系统整体架构
2. 了解架构设计和设计原则
3. 学习基础设施层，理解基础服务的使用
4. 理解核心层，掌握 AI 核心能力和编排
5. 掌握平台层，了解平台服务的暴露方式
6. 实践应用层，开发面向用户的应用

---

### 安装

**安装所有层**：
- 基础设施层提供基础服务
- 核心层提供 AI 能力
- 平台层提供平台服务
- 应用层提供用户界面

**依赖管理**：
- 确保环境配置正确
- 安装必需的系统依赖
- 配置环境变量

---

## 技术栈

| 层级 | 技术栈 |
|------|--------|
| **infra** | PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ, FAISS, Milvus |
| **core** | LangGraph, LangChain, Anthropic API, OpenAI API |
| **platform** | FastAPI, OAuth2, JWT, Prometheus, Grafana |
| **app** | React, Vue, Click, WebSocket |

---

## 相关链接

- [项目 README](../README.md)
- [开发规范](guides/DEVELOPMENT.md) - 代码规范、提交规范、分支策略、PR流程
- [部署指南](guides/DEPLOYMENT.md) - 部署架构、环境管理、监控告警、故障排查

---

*最后更新: 2026-04-13*
