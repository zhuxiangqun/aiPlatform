# 统一错误处理体系

> 提供统一的错误类型定义、错误码、错误处理策略

---

## 🎯 设计目标

统一错误处理体系需要解决：
- 错误类型不统一，难以识别和处理
- 错误信息过于简单，缺少上下文
- 错误传播链不清晰，难以追踪
- 错误处理策略不一致，导致行为不可预测

---

## 📖 错误类型层级

```
CoreError (基类, 位于 core/exceptions.py)
├── AgentError (智能体错误)
│   ├── AgentInitializationError (初始化错误)
│   ├── AgentExecutionError (执行错误)
│   ├── AgentTimeoutError (超时错误)
│   └── AgentStateError (状态错误)
├── MemoryError (记忆错误)
│   ├── MemoryStoreError (存储错误)
│   ├── MemoryRetrieveError (检索错误)
│   └── MemoryOverflowError (溢出错误)
├── ModelError (模型错误)
│   ├── ModelConnectionError (连接错误)
│   ├── ModelTimeoutError (超时错误)
│   ├── ModelRateLimitError (限流错误)
│   └── ModelResponseError (响应错误)
├── SkillError (技能错误)
│   ├── SkillNotFoundError (技能不存在)
│   ├── SkillExecutionError (执行错误)
│   └── SkillTimeoutError (超时错误)
├── ToolError (工具错误)
│   ├── ToolNotFoundError (工具不存在)
│   ├── ToolExecutionError (执行错误)
│   └── ToolTimeoutError (超时错误)
├── KnowledgeError (知识错误)
│   ├── KnowledgeIndexError (索引错误)
│   └── KnowledgeRetrieveError (检索错误)
└── OrchestrationError (编排错误)
    ├── WorkflowError (工作流错误)
    ├── WorkflowTimeoutError (工作流超时)
    └── StepExecutionError (步骤执行错误)
```

> **注意**：当前所有异常类定义在 `core/exceptions.py` 单一文件中。基础设施层和平台层的异常类尚未实现，后续版本将扩展为按模块分文件的组织方式。

---

## 📖 错误码定义

### 错误码格式

```
{模块}{错误序号}

模块码：
- AG: 智能体 (Agent)
- MM: 记忆 (Memory)
- MD: 模型 (Model)
- SK: 技能 (Skill)
- TL: 工具 (Tool)
- KN: 知识 (Knowledge)
- OR: 编排 (Orchestration)

示例：
- AG001: 智能体初始化错误
- AG002: 智能体执行错误
- MD001: 模型连接错误
```

### 错误码表

| 错误码 | 错误类型 | 说明 | HTTP状态码 |
|--------|----------|------|-----------|
| **智能体错误** | | | |
| AG000 | AgentError | 智能体错误基类 | 500 |
| AG001 | AgentInitializationError | 智能体初始化失败 | 500 |
| AG002 | AgentExecutionError | 智能体执行失败 | 500 |
| AG003 | AgentTimeoutError | 智能体执行超时 | 504 |
| AG004 | AgentStateError | 智能体状态错误 | 500 |
| **记忆错误** | | | |
| MM000 | MemoryError | 记忆错误基类 | 500 |
| MM001 | MemoryStoreError | 记忆存储失败 | 500 |
| MM002 | MemoryRetrieveError | 记忆检索失败 | 500 |
| MM003 | MemoryOverflowError | 记忆溢出 | 500 |
| **模型错误** | | | |
| MD000 | ModelError | 模型错误基类 | 500 |
| MD001 | ModelConnectionError | 模型连接失败 | 500 |
| MD002 | ModelTimeoutError | 模型调用超时 | 504 |
| MD003 | ModelRateLimitError | 触发模型限流 | 429 |
| MD004 | ModelResponseError | 模型响应错误 | 500 |
| **技能错误** | | | |
| SK000 | SkillError | 技能错误基类 | 500 |
| SK001 | SkillNotFoundError | 技能不存在 | 404 |
| SK002 | SkillExecutionError | 技能执行失败 | 500 |
| SK003 | SkillTimeoutError | 技能执行超时 | 504 |
| **工具错误** | | | |
| TL000 | ToolError | 工具错误基类 | 500 |
| TL001 | ToolNotFoundError | 工具不存在 | 404 |
| TL002 | ToolExecutionError | 工具执行失败 | 500 |
| TL003 | ToolTimeoutError | 工具执行超时 | 504 |
| **知识错误** | | | |
| KN000 | KnowledgeError | 知识错误基类 | 500 |
| KN001 | KnowledgeIndexError | 知识索引错误 | 500 |
| KN002 | KnowledgeRetrieveError | 知识检索失败 | 500 |
| **编排错误** | | | |
| OR000 | OrchestrationError | 编排错误基类 | 500 |
| OR001 | WorkflowError | 工作流错误 | 500 |
| OR002 | WorkflowTimeoutError | 工作流超时 | 504 |
| OR003 | StepExecutionError | 步骤执行失败 | 500 |

> **规划中**：基础设施层（Database/LLM/VectorStore）和平台层（Auth/RateLimit/Tenant/API）的错误码将在对应模块实现后补充。

---

## 📖 错误基类定义

### 错误基类

**位置**：`core/exceptions.py`

**错误基类 CoreError**

定义统一错误结构：

- **消息**：错误描述文本
- **错误码**：唯一标识错误类型（如 AG002）
- **严重程度**：LOW / MEDIUM / HIGH / CRITICAL（ErrorSeverity 枚举）
- **类别**：INFRA / CORE / PLATFORM（ErrorCategory 枚举）
- **上下文**：错误相关数据字典
- **错误ID**：唯一标识错误实例（UUID）
- **时间戳**：错误发生时间
- **原始异常**：导致错误的原始异常（cause）

**转换方法**：

- to_dict()：转换为字典格式

**使用示例**：

```python
from core.exceptions import AgentExecutionError, ErrorSeverity

# 创建异常
error = AgentExecutionError(
    message="Agent execution failed",
    details={"agent_id": "agent-001", "task": "data_analysis"},
    severity=ErrorSeverity.HIGH
)

# 转换为字典
error_dict = error.to_dict()
# {'error_id': '...', 'error_code': 'AG002', 'message': 'Agent execution failed', ...}
```

---

## 📖 基础设施层错误

### 数据库错误

**位置**：`core/exceptions.py`

**数据库错误类型（已实现）**

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| DatabaseError | INF100 | 数据库错误基类 |
| DatabaseConnectionError | INF101 | 连接失败 |
| DatabaseTimeoutError | INF102 | 查询超时 |
| DatabaseQueryError | INF103 | SQL 执行错误 |

所有错误继承自 RangenError，包含错误消息、错误码、上下文和原始异常。

### LLM错误

**位置**：`core/exceptions.py`

**模型错误类型（已实现）**

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| ModelError | MD000 | 模型错误基类 |
| ModelConnectionError | MD001 | 连接失败 |
| ModelTimeoutError | MD002 | 超时错误 |
| ModelRateLimitError | MD003 | 限流错误 |
| ModelResponseError | MD004 | 响应错误 |

---

## 📖 核心层错误

### Agent错误（已实现）

**Agent 错误类型**

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| AgentError | AG000 | 智能体错误基类 |
| AgentInitializationError | AG001 | 智能体初始化失败 |
| AgentExecutionError | AG002 | 智能体执行失败 |
| AgentTimeoutError | AG003 | 智能体执行超时 |
| AgentStateError | AG004 | 智能体状态错误 |

---

## 📖 平台层错误（已实现）

### 认证错误（已实现）

**位置**：`core/exceptions.py`

**认证错误类型（已实现）**

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| AuthError | PLT100 | 认证错误基类 |
| AuthTokenExpiredError | PLT101 | Token 已过期 |
| AuthPermissionDeniedError | PLT102 | 权限不足 |

### 限流与租户错误（已实现）

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| RateLimitError | PLT200 | 触发限流 |
| TenantError | PLT300 | 租户错误基类 |
| TenantNotFoundError | PLT301 | 租户不存在 |
| TenantQuotaExceededError | PLT302 | 配额超限 |

### API错误（已实现）

| 错误类型 | 错误码 | 说明 |
|----------|--------|------|
| APIError | PLT400 | API错误基类 |
| APINotFoundError | PLT401 | API不存在 |
| APIValidationError | PLT402 | 参数验证失败 |

---

## 📖 错误处理器

### 统一错误处理器

**位置**：`core/exceptions.py`

**统一错误处理器 ErrorHandler**

核心能力：

- **错误分类处理**：区分 CoreError 和未知错误，分别处理
- **上下文合并**：将传入上下文与错误上下文合并
- **错误计数**：自动统计各类错误发生次数
- **响应转换**：转换为统一字典格式

**使用示例**：

```python
from core.exceptions import get_error_handler, AgentExecutionError

handler = get_error_handler()

try:
    # ... agent execution ...
    pass
except AgentExecutionError as e:
    response = handler.handle(e, context={"request_id": "req-001"})
    # response: {'error_id': '...', 'error_code': 'AG002', ...}

# 获取错误统计
stats = handler.get_stats()
# {'AG002': 1, ...}
```

---

## 📖 错误处理最佳实践

### 1. 错误捕获和转换

**错误捕获和转换原则**：

- 核心层：捕获原始异常并转换为自定义错误（CoreError 子类）
- 应用层：使用 CoreError 提供的上下文信息进行错误处理
- 错误转换：保留原始异常作为 cause，便于追踪

### 2. 错误链追踪

**错误链追踪原则**：

- 保留原始异常：在包装新错误时，将原始异常作为 cause 传入
- 自动追踪：CoreError 支持 error_id 和 timestamp 自动生成
- 错误传播：上层错误包含下层错误信息

### 3. 错误恢复策略

**错误恢复策略**：

- 限流错误（ModelRateLimitError）：等待后重试，使用 retry_after 参数
- 超时错误（ModelTimeoutError）：直接重试，设置最大重试次数
- 重试机制：根据错误类型选择不同的重试策略

---

## 📁 文件结构

```
core/
└── exceptions.py               # 所有异常类定义 + ErrorHandler
    # Core 层：
    # - CoreError (基类, 含 error_id/error_code/severity/category/to_dict)
    # - AgentError, MemoryError, ModelError
    # - SkillError, ToolError, KnowledgeError
    # - OrchestrationError
    #
    # Infra 层：
    # - DatabaseError, LLMError, VectorStoreError
    #
    # Platform 层：
    # - AuthError, RateLimitError, TenantError, APIError
    #
    # ErrorHandler (统一错误处理器)
```

---

*最后更新: 2026-04-14*