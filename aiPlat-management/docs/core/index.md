# 核心能力层管理（Layer 1）

> Agent执行引擎、技能系统、记忆系统、知识库的完整运维能力

---

## 一、模块概览

核心能力层管理系统提供从智能体到知识库的完整运维能力：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        核心能力层运维边界                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  智能体框架层（Harness）                                                    │
│  ├── 执行系统（Execution）- Agent循环、重试、Hook拦截                       │
│  ├── 协调系统（Coordination）- 多Agent协作、6种模式                         │
│  ├── 观察系统（Observability）- 监控、指标、事件                             │
│  └── 反馈循环（Feedback Loops）- LOCAL/PUSH/PROD三层反馈                    │
│                                                                             │
│  智能体应用层（Apps）                                                        │
│  ├── Agents - Agent实例管理、生命周期控制                                   │
│  ├── Skills - Skill注册、执行、版本管理                                     │
│  └── Tools - Tool注册、权限控制、调用监控                                   │
│                                                                             │
│  记忆系统层（Memory）                                                        │
│  ├── 短期记忆 - 会话上下文、临时状态                                        │
│  ├── 长期记忆 - 经验积累、知识存储                                          │
│  └── 会话管理 - 多会话、持久化                                              │
│                                                                             │
│  知识管理层（Knowledge）                                                    │
│  ├── 知识库管理 - 集合创建、配置更新                                        │
│  ├── 文档管理 - 上传、解析、分块                                            │
│  └── 索引管理 - 向量索引、检索优化                                          │
│                                                                             │
│  适配器层（Adapters）                                                       │
│  ├── LLM适配器 - OpenAI/Anthropic/本地模型                                  │
│  └── 配置管理 - API密钥、模型参数、限流策略                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 0. Engine vs Workspace（对外应用库分离）

为使“核心能力层稳定可控”且“对外能力可定制可管理”，管理系统将目录化的 Agent / Skill / MCP 分成两套 scope：

| scope | 面向对象 | 默认目录 | 管理入口（前端） | API（management） |
|------|----------|----------|------------------|-------------------|
| **engine** | 核心能力层内部使用 | `aiPlat-core/core/engine/{skills,agents,mcps}` | `/core/*` | `/api/core/skills`、`/api/core/agents`、`/api/core/mcp/servers` |
| **workspace** | 对外/用户/应用库 | `~/.aiplat/{skills,agents,mcps}` | `/workspace/*` | `/api/core/workspace/*` |

说明：
- **执行控制权始终在 core 引擎**（Harness/Runtime），分离仅影响“内容来源与权限边界”。
- **禁止覆盖**：workspace 不允许创建与 engine 同名（同 id）的内容。

## 二、功能模块

### 2.1 执行引擎管理

**文档**：[harness.md](./harness.md)

**核心功能**：
- Agent执行引擎状态监控
- 执行循环配置（循环次数、超时时间）
- Hook拦截器管理
- 执行日志与追踪
- 多Agent协调模式管理
- 反馈循环配置

**界面预览**：
- 执行引擎状态总览
- 执行循环配置面板
- Hook拦截器管理
- 执行日志查询
- 协调模式配置

---

### 2.2 智能体管理

**文档**：[agents.md](./agents.md)

**核心功能**：
- Agent实例生命周期管理
- Agent配置与参数调优
- Agent执行监控
- Agent性能分析
- Agent版本管理

**界面预览**：
- Agent列表（状态、执行数、成功率）
- Agent详情（配置、历史执行、性能指标）
- 创建Agent向导
- Agent执行日志

---

### 2.3 技能管理

**文档**：[skills.md](./skills.md)

**核心功能**：
- Skill注册与版本管理
- Skill执行监控
- Skill配置与参数
- Skill依赖管理
- Skill性能分析

**界面预览**：
- Skill列表（分类、状态、调用统计）
- Skill详情（配置、历史执行、性能）
- 注册Skill弹窗
- Skill版本管理

---

### 2.4 记忆系统管理

**文档**：[memory.md](./memory.md)

**核心功能**：
- 会话管理（创建/删除/查询）
- 记忆存储状态监控
- 记忆清理策略配置
- 记忆统计分析
- 记忆导入导出

**界面预览**：
- 会话列表（活跃会话、历史会话）
- 记忆存储统计（大小、条目数）
- 会话详情（上下文内容）
- 记忆清理配置

---

### 2.5 知识库管理

**文档**：[knowledge.md](./knowledge.md)

**核心功能**：
- 知识库生命周期管理
- 文档上传与解析
- 向量索引管理
- 检索测试与优化
- 知识库统计分析

**界面预览**：
- 知识库列表（集合数、文档数、大小）
- 知识库详情（配置、索引状态）
- 文档管理（上传、解析状态）
- 检索测试工具

---

### 2.6 适配器管理

**文档**：[adapters.md](./adapters.md)

**核心功能**：
- LLM适配器配置
- API密钥管理
- 模型参数配置
- 调用监控与限流
- 连接测试

**界面预览**：
- 适配器列表（Provider、状态、调用统计）
- 适配器详情（配置、模型列表）
- API密钥管理
- 调用监控图表

---

## 三、运维能力矩阵

| 模块 | 查看能力 | 操作能力 | 监控能力 | 告警能力 |
|------|---------|---------|---------|---------|
| 执行引擎管理 | ✅ | ✅ | ✅ | ✅ |
| 智能体管理 | ✅ | ✅ | ✅ | ✅ |
| 技能管理 | ✅ | ✅ | ✅ | ✅ |
| 记忆系统管理 | ✅ | ✅ | ✅ | ✅ |
| 知识库管理 | ✅ | ✅ | ✅ | ✅ |
| 适配器管理 | ✅ | ✅ | ✅ | ✅ |

---

## 四、用户角色

| 角色 | 权限 |
|------|------|
| **运维工程师** | 全部模块的完整操作权限 |
| **开发工程师** | Agent/Skill/Tool的查看和配置权限 |
| **数据工程师** | 知识库管理的完整操作权限 |
| **访客** | 所有模块的只读权限 |

---

## 五、实施状态

| 层级 | 管理系统覆盖 | 实施状态 |
|------|-------------|---------|
| **Layer 0 - 基础设施层** | 完整运维能力 | ✅ 已实施 |
| **Layer 1 - 核心能力层** | 完整运维能力 | ✅ 已实施 |
| **Layer 2 - 平台服务层** | 预留管理接口 | 🔜 待实施 |
| **Layer 3 - 应用接入层** | 预留管理接口 | 🔜 待实施 |

---

### 5.1 API 实现状态

| 模块 | API 端点 | 实现状态 |
|------|---------|---------|
| **执行引擎管理** | GET /harness/status | ✅ 已实现 |
| | GET/PUT /harness/config | ✅ 已实现 |
| | GET /harness/logs | ✅ 已实现 |
| | GET /harness/metrics | ✅ 已实现 |
| | GET /harness/hooks | ✅ 已实现 |
| | POST/DELETE /harness/hooks/{id} | ✅ 已实现 |
| **智能体管理** | GET/POST /agents | ✅ 已实现 |
| | GET/PUT/DELETE /agents/{id} | ✅ 已实现 |
| | POST /agents/{id}/start | ✅ 已实现 |
| | POST /agents/{id}/stop | ✅ 已实现 |
| | GET /agents/{id}/skills | ✅ 已实现 |
| | POST/DELETE /agents/{id}/skills/{id} | ✅ 已实现 |
| | GET /agents/{id}/tools | ✅ 已实现 |
| | POST/DELETE /agents/{id}/tools/{id} | ✅ 已实现 |
| | GET /agents/{id}/history | ✅ 已实现 |
| **技能管理** | GET/POST /skills | ✅ 已实现 |
| | GET/PUT/DELETE /skills/{id} | ✅ 已实现 |
| | POST /skills/{id}/enable | ✅ 已实现 |
| | POST /skills/{id}/disable | ✅ 已实现 |
| | GET /skills/{id}/agents | ✅ 已实现 |
| | GET /skills/{id}/binding-stats | ✅ 已实现 |
| **记忆系统管理** | GET/POST /memory/sessions | ✅ 已实现 |
| | GET/DELETE /memory/sessions/{id} | ✅ 已实现 |
| | GET /memory/stats | ✅ 已实现 |
| **知识库管理** | GET/POST /knowledge/collections | ✅ 已实现 |
| | GET/PUT/DELETE /knowledge/collections/{id} | ✅ 已实现 |
| **适配器管理** | GET/POST /adapters | ✅ 已实现 |
| | GET/PUT/DELETE /adapters/{id} | ✅ 已实现 |
| | POST /adapters/{id}/test | ✅ 已实现 |

### 5.2 前端实现状态

| 模块 | 页面 | 实现状态 |
|------|------|---------|
| **执行引擎管理** | 执行引擎状态 | 🔜 待实现 |
| | 执行配置管理 | 🔜 待实现 |
| | 执行日志查询 | 🔜 待实现 |
| **智能体管理** | Agent列表 | 🔜 待实现 |
| | Agent详情 | 🔜 待实现 |
| | 创建Agent | 🔜 待实现 |
| **技能管理** | Skill列表 | 🔜 待实现 |
| | Skill详情 | 🔜 待实现 |
| | 注册Skill | 🔜 待实现 |
| **记忆系统管理** | 会话列表 | 🔜 待实现 |
| | 记忆统计 | 🔜 待实现 |
| | 会话详情 | 🔜 待实现 |
| **知识库管理** | 知识库列表 | 🔜 待实现 |
| | 文档管理 | 🔜 待实现 |
| | 检索测试 | 🔜 待实现 |
| **适配器管理** | 适配器列表 | 🔜 待实现 |
| | 适配器配置 | 🔜 待实现 |
| | 调用监控 | 🔜 待实现 |

---

## 六、相关文档

### 核心能力层运维模块

- [执行引擎管理](harness.md) - Harness 执行引擎运维
- [智能体管理](agents.md) - Agent 实例管理
- [技能管理](skills.md) - Skill 注册与执行
- [记忆系统管理](memory.md) - 会话与记忆管理
- [知识库管理](knowledge.md) - 知识库与文档管理
- [适配器管理](adapters.md) - LLM适配器配置

### 其他层级

- [系统总览](../index.md) - Management 系统架构
- [基础设施层管理](../infra/index.md) - Layer 0 管理接口
- [平台服务层管理](../platform/index.md) - Layer 2 管理接口
- [应用接入层管理](../app/index.md) - Layer 3 管理接口

---

## 七、技术实现

### 后端 API

```
/api/core/
├── /harness                   # 执行引擎管理
│   ├── GET /status            # 获取引擎状态
│   ├── GET/PUT /config        # 配置管理
│   ├── GET /metrics           # 指标查询
│   └── GET /logs              # 执行日志
│
├── /agents                    # 智能体管理
│   ├── GET /                  # 获取Agent列表
│   ├── POST /                 # 创建Agent
│   ├── GET /{id}              # 获取Agent详情
│   ├── PUT /{id}              # 更新Agent配置
│   ├── DELETE /{id}           # 删除Agent
│   ├── POST /{id}/execute     # 执行Agent
│   └── GET /{id}/history      # 执行历史
│
├── /skills                    # 技能管理
│   ├── GET /                  # 获取Skill列表
│   ├── POST /                 # 注册Skill
│   ├── GET /{id}              # 获取Skill详情
│   ├── PUT /{id}              # 更新Skill配置
│   ├── DELETE /{id}           # 注销Skill
│   └── POST /{id}/execute     # 执行Skill
│
├── /memory                    # 记忆系统管理
│   ├── /sessions              # 会话管理
│   │   ├── GET /              # 获取会话列表
│   │   ├── POST /             # 创建会话
│   │   ├── GET /{id}          # 获取会话详情
│   │   └── DELETE /{id}       # 删除会话
│   └── GET /stats             # 记忆统计
│
├── /knowledge                 # 知识库管理
│   ├── /collections           # 知识库集合
│   │   ├── GET /              # 获取集合列表
│   │   ├── POST /             # 创建集合
│   │   ├── GET /{id}          # 获取集合详情
│   │   ├── PUT /{id}          # 更新集合配置
│   │   └── DELETE /{id}       # 删除集合
│   ├── /documents             # 文档管理
│   │   ├── POST /             # 上传文档
│   │   ├── GET /{id}          # 获取文档状态
│   │   └── DELETE /{id}       # 删除文档
│   └── POST /search           # 检索测试
│
└── /adapters                  # 适配器管理
    ├── GET /                  # 获取适配器列表
    ├── POST /                 # 添加适配器
    ├── GET /{type}            # 获取适配器详情
    ├── PUT /{type}            # 更新适配器配置
    └── POST /{type}/test      # 测试连接
```

### 前端路由

```
/core
├── /harness                   # 执行引擎管理
│   ├── /                      # 状态总览
│   ├── /config                # 配置管理
│   └── /logs                  # 执行日志
│
├── /agents                    # 智能体管理
│   ├── /                      # Agent列表
│   ├── /create                # 创建Agent
│   └── /:id                   # Agent详情
│
├── /skills                    # 技能管理
│   ├── /                      # Skill列表
│   ├── /register              # 注册Skill
│   └── /:id                   # Skill详情
│
├── /memory                    # 记忆系统管理
│   ├── /sessions              # 会话管理
│   ├── /stats                 # 记忆统计
│   └── /:sessionId            # 会话详情
│
├── /knowledge                 # 知识库管理
│   ├── /collections           # 知识库列表
│   ├── /collections/:id       # 知识库详情
│   ├── /documents             # 文档管理
│   └── /search                # 检索测试
│
└── /adapters                  # 适配器管理
    ├── /                      # 适配器列表
    ├── /:type                 # 适配器配置
    └── /:type/monitor         # 调用监控
```

---

*最后更新:2026-04-13  
**版本**：v1.0  
**维护团队**：AI Platform Team

---

## 八、架构边界

**重要**：本模块（核心能力层管理）的业务逻辑在 `aiPlat-core` 层实现。

### 8.1 架构关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (5173)                            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP (浏览器)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  aiPlat-management (8000)                           │
│                       管理系统层                                    │
│  management/api/core.py:                                           │
│  - HTTP 转发到 aiPlat-core 管理接口                                 │
│  - 不包含业务逻辑实现                                               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ HTTP 调用 (httpx)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     aiPlat-core (8002)                              │
│                       核心能力业务层                                │
│  core/harness/:                                                     │
│  - execution/ - 执行系统                                            │
│  - coordination/ - 协调系统                                         │
│  - observability/ - 观察系统                                        │
│  - feedback_loops/ - 反馈循环                                      │
│  core/apps/:                                                        │
│  - agents/ - Agent 实现                                             │
│  - skills/ - Skill 实现                                             │
│  - tools/ - Tool 实现                                               │
│  core/harness/:                                                     │
│  - memory/ - 记忆系统                                               │
│  - knowledge/ - 知识管理                                            │
│  core/adapters/:                                                    │
│  - llm/ - LLM 适配器                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 API 端点对应

| 管理界面 | Management API | Core API | 实现位置 |
|----------|----------------|----------|----------|
| 执行引擎管理 | `/api/core/harness` | `/api/management/harness` | `core/harness/execution/` |
| 智能体管理 | `/api/core/agents` | `/api/management/agents` | `core/apps/agents/` |
| 技能管理 | `/api/core/skills` | `/api/management/skills` | `core/apps/skills/` |
| 记忆系统管理 | `/api/core/memory` | `/api/management/memory` | `core/harness/memory/` |
| 知识库管理 | `/api/core/knowledge` | `/api/management/knowledge` | `core/harness/knowledge/` |
| 适配器管理 | `/api/core/adapters` | `/api/management/adapters` | `core/adapters/llm/` |

### 8.3 启动顺序

```bash
# 1. 先启动基础设施层
cd aiPlat-infra && ./start.sh  # 端口 8001

# 2. 再启动核心能力层
cd aiPlat-core && ./start.sh  # 端口 8002

# 3. 最后启动管理系统层
cd aiPlat-management && ./start.sh # 端口 8000
```

### 8.4 开发指南

**添加新的管理功能**：
1. 在 `aiPlat-core/core/` 添加管理管理器类
2. 在 `aiPlat-core` 暴露 REST API 端点
3. 在 `aiPlat-management/management/core_client.py` 添加 HTTP 客户端方法
4. 在 `aiPlat-management/management/api/core.py` 添加 API 转发

详细架构说明：[architecture-boundary.md](../architecture-boundary.md)
