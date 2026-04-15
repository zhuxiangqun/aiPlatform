# 📚 infra 文档索引

> 基础设施层 - Layer 0，管理和抽象所有基础设施资源

---

## 🎯 模块定位

**职责**：管理和抽象所有基础设施资源，包括硬件资源（计算、内存、存储、网络）和软件服务（数据库、LLM、消息队列），完全独立，不依赖任何内部模块。

**依赖方向**：
```
aiPlat-infra 不依赖任何内部包
  ↓
可以被所有上层导入（core, platform, app）
```

**设计原则**：
- ✅ 提供接口和默认实现
- ✅ 支持多种后端（PostgreSQL/MySQL, OpenAI/Anthropic）
- ✅ 配置驱动，易于替换
- ✅ 无状态或状态透明

**管理接口**：
- aiPlat-infra 提供的管理接口可被 **aiPlat-management** 调用
- 管理接口包括：状态查询、指标采集、健康检查、配置管理
- 详见：[管理模块文档](management/index.md)

---

## 🏗️ 基础设施层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        aiPlat-infra                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      资源管理层                               │    │
│  ├───────────────┬───────────────┬───────────────┬─────────────┤    │
│  │  计算资源      │  内存资源      │  存储资源      │  网络资源    │    │
│  │  - CPU池       │  - 多级缓存    │  - 本地存储    │  - 服务发现  │    │
│  │  - GPU池       │  - 内存池      │  - 网络存储    │  - 负载均衡  │    │
│  │  - 任务队列    │  - 显存管理    │  - 生命周期    │  - 网络策略  │    │
│  │  - 弹性扩缩    │  - OOM防护     │               │             │    │
│  └───────────────┴───────────────┴───────────────┴─────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      服务抽象层                               │    │
│  ├───────────────┬───────────────┬───────────────┬─────────────┤    │
│  │  数据库        │  LLM服务       │  向量存储      │  消息队列    │    │
│  │  - PostgreSQL │  - 模型管理    │  - Milvus     │  - Kafka    │    │
│  │  - MySQL      │  - 推理引擎    │  - FAISS      │  - RabbitMQ │    │
│  │  - MongoDB    │  - 模型量化    │  - Pinecone   │  - Redis    │    │
│  │               │  - 推测解码    │               │             │    │
│  └───────────────┴───────────────┴───────────────┴─────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      可观测性层                               │    │
│  ├───────────────┬───────────────┬───────────────┬─────────────┤    │
│  │  日志          │  监控          │  追踪          │  告警        │    │
│  │  - 结构化日志  │  - 指标采集    │  - 分布式追踪  │  - 告警规则  │    │
│  │  - 日志聚合    │  - 健康检查    │  - 性能分析    │  - 通知渠道  │    │
│  └───────────────┴───────────────┴───────────────┴─────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      配置与编排层                             │    │
│  ├───────────────┬───────────────┬───────────────┬─────────────┤    │
│  │  配置管理      │  容器编排      │  资源配额      │  环境管理    │    │
│  │  - 文件配置    │  - K8s        │  - 租户配额    │  - 命名空间  │    │
│  │  - 环境变量    │  - Docker     │  - 资源限制    │  - 环境隔离  │    │
│  │  - 配置中心    │  - 自动扩缩    │  - 计费统计    │             │    │
│  └───────────────┴───────────────┴───────────────┴─────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 快速导航

### 👥 按角色

| 角色 | 文档目录 |
|------|---------|
| 架构师 | [by-role/architect/index.md](by-role/architect/index.md) - 架构设计、依赖管理 |
| 开发者 | [by-role/developer/index.md](by-role/developer/index.md) - 开发指南、最佳实践 |
| 运维 | [by-role/ops/index.md](by-role/ops/index.md) - 部署运维、监控配置 |
| 用户 | [by-role/user/index.md](by-role/user/index.md) - 使用指南、API 文档 |

---

## 📖 各角色文档内容说明

| 角色 | 文档目录 | 包含内容 |
|------|----------|----------|
| 架构师 | `by-role/architect/` | 架构设计理念、技术选型依据、模块划分原则、依赖关系管理、扩展机制设计 |
| 开发者 | `by-role/developer/` | 开发环境搭建、模块开发流程、核心模块使用、最佳实践、测试指南、调试技巧 |
| 运维 | `by-role/ops/` | 部署拓扑、配置参数说明、监控指标、告警规则、故障排查、备份恢复、安全管理 |
| 用户 | `by-role/user/` | 快速开始、核心概念、使用指南、API 使用、配置示例 |

---

## 📖 核心模块

### 资源管理模块

| 模块 | 说明 | 文档 |
|------|------|------|
| **compute** | CPU/GPU 资源管理、任务调度、弹性扩缩 | [📄 compute](compute/index.md) |
| **memory** | 多级缓存、内存池、显存管理、OOM 防护 | [📄 memory](memory/index.md) |
| **storage** | 本地存储、对象存储（S3/GCS/Azure）、生命周期管理 | [📄 storage](storage/index.md) |
| **network** | 服务发现、负载均衡、网络策略 | [📄 network](network/index.md) |

### 数据存储模块

| 模块 | 说明 | 文档 |
|------|------|------|
| **database** | 数据库抽象层（PostgreSQL/MySQL/MongoDB）| [📄 database](database/index.md) |
| **vector** | 向量数据库接口（FAISS/Milvus/Pinecone）| [📄 vector](vector/index.md) |

### 核心服务模块

| 模块 | 说明 | 文档 |
|------|------|------|
| **llm** | LLM 客户端接口（OpenAI/Anthropic/DeepSeek）+ 模型管理 | [📄 llm](llm/index.md) |
| **messaging** | 消息队列抽象（Kafka/RabbitMQ/Redis）| [📄 messaging](messaging/index.md) |
| **config** | 配置管理（文件/环境/Consul）| [📄 config](config/index.md) |
| **logging** | 结构化日志系统 | [📄 logging](logging/index.md) |

### 可观测性模块

| 模块 | 说明 | 文档 |
|------|------|------|
| **monitoring** | 系统监控（指标采集/健康检查）| [📄 monitoring](monitoring/index.md) |
| **observability** | 可观测性（分布式追踪/日志聚合）| [📄 observability](observability/index.md) |

### 网络和工具模块

| 模块 | 说明 | 文档 |
|------|------|------|
| **http** | HTTP 客户端（重试、超时、连接池）| [📄 http](http/index.md) |
| **mcp** | MCP 协议客户端（工具调用、协议解析）| [📄 mcp](mcp/index.md) |
| **cache** | 缓存客户端（Redis/内存/文件）| [📄 cache](cache/index.md) |
| **utils** | 通用工具函数 | [📄 utils](utils/index.md) |
| **di** | 依赖注入容器（用于 infra 内部模块管理）| [📄 di](di/index.md) |

> **说明**：di 模块提供轻量级 DI 容器，用于 infra 层内部模块之间的依赖管理。与框架级 DI（如 FastAPI）不冲突：infra 内部使用自带的 DI 容器，上层通过工厂接口获取 infra 实例。

---

## 🧪 测试文档

### 测试体系

**项目级测试指南**：[系统测试指南](../../docs/TESTING_GUIDE.md) - 测试策略、分层测试方法、跨层测试规范

**infra层测试文档**：

| 文档 | 说明 | 适合人群 |
|------|------|---------|
| [测试快速开始](testing/TESTING_QUICKSTART.md) | 5分钟快速上手测试 | 所有人 👈 从这里开始 |
| [测试最佳实践](testing/TESTING_GUIDE.md) | 如何编写好的测试 | 开发者 |
| [详细测试指南](testing/INFRA_DETAILED_TESTING_GUIDE.md) | infra层完整测试策略 | 测试工程师、架构师 |
| [测试检查清单](testing/TESTING_CHECKLIST.md) | 快速质量检查 | 开发者、Code Review |

### 测试报告

| 报告 | 内容 | 状态 |
|------|------|------|
| [数据库集成测试报告](testing/reports/DATABASE_INTEGRATION_REPORT.md) | PostgreSQL/MySQL/MongoDB测试结果 | ✅ 完成 |
| [消息系统集成测试报告](testing/reports/MESSAGING_INTEGRATION_REPORT.md) | Redis Streams测试结果 | ✅ 完成 |
| [测试总结](testing/reports/TESTCONTAINERS_FINAL_REPORT.md) | Testcontainers实施总结 | ✅ 完成 |

### 测试状态

- ✅ **单元测试**: 46/46 通过 (100%)
- ✅ **集成测试**: 5/5 通过 (数据库3 + 消息2)
- ✅ **代码覆盖率**: 基础设施层 85%+
- ✅ **测试文档**: 完整覆盖

---

## 📖 核心接口定义

### DatabaseClient 接口

**位置**：`infra/database/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute` | `query: str`, `params: dict` | `List[dict]` | 执行查询，返回结果列表 |
| `execute_many` | `query: str`, `params_list: List[dict]` | `List[Any]` | 批量执行，返回结果列表 |
| `transaction` | 无 | `AsyncContextManager` | 获取事务上下文管理器 |
| `close` | 无 | `None` | 关闭连接 |

**支持的后端**：
- `postgres`：PostgreSQL（推荐）
- `mysql`：MySQL
- `mongodb`：MongoDB

---

### LLMClient 接口

**位置**：`infra/llm/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `chat` | `messages: List[Message]`, `**kwargs` | `ChatResponse` | 对话接口，返回生成的回复 |
| `embed` | `texts: List[str]` | `List[List[float]]` | 文本向量化，返回向量列表 |
| `count_tokens` | `text: str` | `int` | 统计文本的 Token 数量 |

**数据模型**：

| 模型 | 字段 | 说明 |
|------|------|------|
| `Message` | `role: str`, `content: str` | 消息对象 |
| `ChatResponse` | `content: str`, `usage: dict` | 对话响应 |

**支持的提供商**：
- `openai`：OpenAI（GPT-4、GPT-3.5）
- `anthropic`：Anthropic（Claude）
- `deepseek`：DeepSeek
- `mock`：Mock 实现（用于测试）

---

### VectorStore 接口

**位置**：`infra/vector/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add` | `vectors: List[Vector]`, `metadata: List[dict]` | `List[str]` | 添加向量，返回 ID 列表 |
| `search` | `query_vector: List[float]`, `top_k: int` | `List[SearchResult]` | 相似度搜索，返回结果列表 |
| `delete` | `ids: List[str]` | `bool` | 删除向量，返回是否成功 |
| `get` | `id: str` | `Vector` | 获取单个向量 |

**数据模型**：

| 模型 | 字段 | 说明 |
|------|------|------|
| `Vector` | `id: str`, `values: List[float]`, `metadata: dict` | 向量对象 |
| `SearchResult` | `id: str`, `score: float`, `metadata: dict` | 搜索结果 |

**支持的后端**：
- `milvus`：Milvus（推荐，生产环境）
- `faiss`：FAISS（本地开发）
- `pinecone`：Pinecone（云端托管）

---

### CacheClient 接口

**位置**：`infra/cache/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get` | `key: str` | `Any` | 获取缓存值 |
| `set` | `key: str`, `value: Any`, `ttl: int` | `bool` | 设置缓存值，TTL单位秒 |
| `delete` | `key: str` | `bool` | 删除缓存值 |
| `exists` | `key: str` | `bool` | 检查键是否存在 |

**支持的后端**：
- `redis`：Redis（推荐）
- `memory`：本地内存（开发测试）

---

## 🏭 工厂函数

### 数据库工厂

**位置**：`infra/database/factory.py`

**函数签名**：
```
create_database_client(config: DatabaseConfig) -> DatabaseClient
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.type` | str | 数据库类型：`postgres`, `mysql`, `mongodb` |
| `config.host` | str | 数据库主机地址 |
| `config.port` | int | 数据库端口 |
| `config.name` | str | 数据库名称 |
| `config.user` | str | 用户名 |
| `config.password` | str | 密码 |
| `config.pool.min_size` | int | 连接池最小连接数 |
| `config.pool.max_size` | int | 连接池最大连接数 |

**使用示例**：
```bash
# 从配置创建客户端
config = DatabaseConfig(
    type="postgres",
    host="localhost",
    port=5432,
    name="ai_platform",
    user="postgres",
    password="password"
)
db = create_database_client(config)

# 执行查询
result = await db.execute("SELECT * FROM users WHERE id = :id", {"id": 1})
```

---

### LLM 工厂

**位置**：`infra/llm/factory.py`

**函数签名**：
```
create_llm_client(config: LLMConfig) -> LLMClient
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.provider` | str | LLM 提供商：`openai`, `anthropic`, `deepseek`, `mock` |
| `config.model` | str | 模型名称：`gpt-4`, `claude-3-opus` 等 |
| `config.api_key` | str | API 密钥 |
| `config.timeout` | int | 超时时间（秒）|
| `config.max_retries` | int | 最大重试次数 |

**使用示例**：
```bash
# 从配置创建客户端
config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_key="sk-...",
    timeout=30,
    max_retries=3
)
llm = create_llm_client(config)

# 对话
response = await llm.chat([
    {"role": "system", "content": "你是一个助手"},
    {"role": "user", "content": "你好"}
])

# 向量化
embeddings = await llm.embed(["hello world"])
```

---

### 向量存储工厂

**位置**：`infra/vector/factory.py`

**函数签名**：
```
create_vector_store(config: VectorConfig) -> VectorStore
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.type` | str | 存储类型：`milvus`, `faiss`, `pinecone` |
| `config.host` | str | 服务地址 |
| `config.port` | int | 服务端口 |
| `config.dimension` | int | 向量维度 |
| `config.collection` | str | 集合名称 |

**使用示例**：
```bash
# 从配置创建存储
config = VectorConfig(
    type="milvus",
    host="localhost",
    port=19530,
    dimension=1536,
    collection="documents"
)
vector_store = create_vector_store(config)

# 添加向量
ids = await vector_store.add(
    vectors=[Vector(values=[0.1, 0.2, ...], metadata={"source": "doc1"})]
)

# 搜索向量
results = await vector_store.search(
    query_vector=[0.1, 0.2, ...],
    top_k=10
)
```

---

## ⚙️ 配置结构

### 配置文件位置

| 环境 | 配置文件路径 |
|------|-------------|
| 开发环境 | `config/infra/development.yaml` |
| 测试环境 | `config/infra/test.yaml` |
| 生产环境 | `config/infra/production.yaml` |

---

### 配置文件示例

**位置**：`config/infra/development.yaml`

```yaml
# 数据库配置
database:
  type: postgres              # postgres, mysql, mongodb
  host: localhost
  port: 5432
  name: ai_platform_dev
  user: ${DB_USER}            # 从环境变量读取
  password: ${DB_PASSWORD}
  
  # 连接池配置
  pool:
    min_size: 5
    max_size: 20
    max_overflow: 10
    timeout: 30
  
  # SSL 配置
  ssl:
    enabled: false
    cert_path: null

# LLM 配置
llm:
  provider: openai            # openai, anthropic, deepseek, mock
  model: gpt-4
  api_key: ${OPENAI_API_KEY}  # 从环境变量读取
  timeout: 30
  max_retries: 3
  
  # 模型参数
  default_params:
    temperature: 0.7
    max_tokens: 2000

# 向量存储配置
vector:
  type: milvus                # milvus, faiss, pinecone
  host: localhost
  port: 19530
  dimension: 1536             # text-embedding-3-small 的维度
  
  # 索引配置
  index:
    type: HNSW                # HNSW, IVF_FLAT, IVF_SQ8
    params:
      m: 16
      ef_construction: 256

# 缓存配置
cache:
  type: redis                 # redis, memory
  host: localhost
  port: 6379
  password: ${REDIS_PASSWORD}
  db: 0
  
  # 连接池配置
  pool:
    max_connections: 50
    retry_on_timeout: true

# 消息队列配置
messaging:
  backend: redis              # kafka, rabbitmq, redis
  hosts:
    - localhost:6379
  topic_prefix: "aiplat"
  client_id: "aiplat-client"
  
  # Redis 配置
  redis:
    db: 0
    password: ${REDIS_PASSWORD}
    pool_size: 10
  
  # Kafka 配置
  # kafka:
  #   consumer_group: "aiplat-consumer"
  #   auto_offset_reset: "latest"
  #   enable_auto_commit: true
  
  # RabbitMQ 配置
  # rabbitmq:
  #   username: guest
  #   password: guest
  #   vhost: /
  #   exchange_type: topic
  #   durable: true

# 日志配置
logging:
  level: INFO                 # DEBUG, INFO, WARNING, ERROR
  format: json                # json, text
  output:
    - console
    - file
  
  # 文件输出配置
  file:
    path: /var/log/ai-platform/infra.log
    max_size: 100MB
    backup_count: 10

# 监控配置
monitoring:
  enabled: true
  port: 9090
  
  # 指标配置
  metrics:
    prefix: ai_platform_infra
    labels:
      env: development
      service: infra
```

---

### 配置优先级

配置加载优先级（从高到低）：

1. **环境变量**：`DATABASE_HOST`, `LLM_API_KEY` 等
2. **远程配置中心**：Consul、Etcd 等（如果启用）
3. **环境配置文件**：`config/infra/{env}.yaml`
4. **默认配置文件**：`config/infra/default.yaml`

**优先级示例**：
```bash
# 环境变量覆盖配置文件
export DATABASE_HOST=production-db.example.com
export LLM_API_KEY=sk-production-key

# 配置文件中的 ${DATABASE_HOST} 和 ${LLM_API_KEY} 会被替换
```

---

## 🚀 使用示例

### 数据库操作

**位置**：`infra/database/examples/basic_usage.py`

**完整示例**：

1. **加载配置**：
```bash
from infra.config import load_config

# 加载配置
config = load_config("config/infra/development.yaml")
```

2. **创建数据库客户端**：
```bash
from infra.database import create_database_client

db = create_database_client(config.database)
```

3. **执行查询**：
```bash
# 查询单条记录
user = await db.execute(
    "SELECT * FROM users WHERE id = :id",
    {"id": 1}
)

# 查询多条记录
users = await db.execute(
    "SELECT * FROM users WHERE created_at > :date",
    {"date": "2026-01-01"}
)
```

4. **执行事务**：
```bash
# 使用事务
async with db.transaction() as tx:
    await tx.execute(
        "UPDATE accounts SET balance = balance - :amount WHERE id = :id",
        {"amount": 100, "id": 1}
    )
    await tx.execute(
        "UPDATE accounts SET balance = balance + :amount WHERE id = :id",
        {"amount": 100, "id": 2}
    )
```

5. **批量操作**：
```bash
# 批量插入
await db.execute_many(
    "INSERT INTO logs (message, level) VALUES (:message, :level)",
    [
        {"message": "Info message 1", "level": "info"},
        {"message": "Info message 2", "level": "info"}
    ]
)
```

---

### LLM 调用

**位置**：`infra/llm/examples/basic_usage.py`

**完整示例**：

1. **创建 LLM 客户端**：
```bash
from infra.llm import create_llm_client
from infra.llm.schemas import Message

llm = create_llm_client(config.llm)
```

2. **对话**：
```bash
# 单轮对话
response = await llm.chat([
    Message(role="system", content="你是一个专业的客服助手"),
    Message(role="user", content="如何重置密码？")
])
print(response.content)

# 多轮对话
messages = [
    Message(role="system", content="你是一个AI助手"),
    Message(role="user", content="你好")
]
response1 = await llm.chat(messages)

# 继续对话
messages.append(Message(role="assistant", content=response1.content))
messages.append(Message(role="user", content="请介绍一下你自己"))
response2 = await llm.chat(messages)
```

3. **向量化**：
```bash
# 批量向量化
texts = ["hello world", "goodbye universe"]
embeddings = await llm.embed(texts)

print(f"第一段文本的前10个维度: {embeddings[0][:10]}")
print(f"向量维度: {len(embeddings[0])}")
```

4. **流式输出**：
```bash
# 流式对话（如果提供商支持）
async for chunk in llm.chat_stream([
    Message(role="user", content="讲一个故事")
]):
    print(chunk.content, end="", flush=True)
```

5. **Token 统计**：
```bash
# 统计 Token 数量
text = "这是一段测试文本"
token_count = await llm.count_tokens(text)
print(f"Token 数量: {token_count}")
```

---

### 向量存储操作

**位置**：`infra/vector/examples/basic_usage.py`

**完整示例**：

1. **创建向量存储**：
```bash
from infra.vector import create_vector_store
from infra.vector.schemas import Vector

vector_store = create_vector_store(config.vector)
```

2. **添加向量**：
```bash
# 添加单个向量
vector = Vector(
    values=[0.1, 0.2, 0.3, ...],  # 1536 维向量
    metadata={"source": "doc1", "page": 1}
)
ids = await vector_store.add([vector])
print(f"添加的向量 ID: {ids}")
```

3. **批量添加**：
```bash
# 批量添加向量
vectors = [
    Vector(values=[0.1, ...], metadata={"source": "doc1"}),
    Vector(values=[0.2, ...], metadata={"source": "doc2"}),
    Vector(values=[0.3, ...], metadata={"source": "doc3"})
]
ids = await vector_store.add(vectors)
```

4. **搜索向量**：
```bash
# 相似度搜索
query_vector = [0.15, 0.25, 0.35, ...]
results = await vector_store.search(query_vector, top_k=5)

for result in results:
    print(f"ID: {result.id}, Score: {result.score}, Metadata: {result.metadata}")
```

5. **删除向量**：
```bash
# 删除向量
await vector_store.delete(ids=["id1", "id2"])
```

---

### 缓存操作

**完整示例**：

```bash
from infra.cache import create_cache_client

# 创建缓存客户端
cache = create_cache_client(config.cache)

# 设置缓存
await cache.set("user:1", {"name": "Alice", "age": 30}, ttl=3600)

# 获取缓存
user = await cache.get("user:1")
print(f"用户信息: {user}")

# 删除缓存
await cache.delete("user:1")

# 检查键是否存在
exists = await cache.exists("user:1")
print(f"键是否存在: {exists}")
```

---

### 消息队列操作

**完整示例**：

```bash
from infra.messaging import create_messaging_client, MessagingConfig, Message

# 创建消息队列客户端
config = MessagingConfig(
    backend="kafka",
    hosts=["localhost:9092"],
    topic_prefix="aiplat"
)
client = create_messaging_client(config)

# 发布消息
async def publish_example():
    await client.publish(
        topic="events.user.created",
        message=b'{"user_id": "123", "name": "Alice"}',
        headers={"source": "api", "version": "1.0"}
    )

# 订阅消息
async def subscribe_example():
    async def handle_message(message: Message):
        print(f"收到消息: {message.body.decode()}")
        print(f"主题: {message.topic}")
        print(f"消息ID: {message.id}")
        # 处理消息...
        await client.ack(message.id)
    
    await client.subscribe(
        topic="events.user.created",
        handler=handle_message
    )

# 关闭连接
await client.close()
```

**不同后端配置示例**：

1. **Kafka 配置**：
```yaml
messaging:
  backend: kafka
  hosts:
    - localhost:9092
  topic_prefix: "aiplat"
  kafka:
    consumer_group: "aiplat-consumer"
    auto_offset_reset: "latest"
    enable_auto_commit: true
```

2. **RabbitMQ 配置**：
```yaml
messaging:
  backend: rabbitmq
  hosts:
    - localhost:5672
  topic_prefix: "aiplat"
  rabbitmq:
    username: guest
    password: guest
    vhost: /
    exchange_type: topic
    durable: true
```

3. **Redis 配置**：
```yaml
messaging:
  backend: redis
  hosts:
    - localhost:6379
  topic_prefix: "aiplat"
  redis:
    db: 0
    password: null
    pool_size: 10
```

---

## 🔧 扩展指南

### 添加新的数据库实现

**步骤**：

1. **创建实现文件**：`infra/database/my_database.py`

2. **实现接口**：
```bash
from infra.database.base import DatabaseClient

class MyDatabaseClient(DatabaseClient):
    def __init__(self, config: MyDatabaseConfig):
        self.config = config
        # 初始化连接
    
    async def execute(self, query: str, params: dict = None) -> List[dict]:
        # 实现查询逻辑
    
    async def execute_many(self, query: str, params_list: List[dict]) -> List[Any]:
        # 实现批量查询逻辑
    
    async def transaction(self) -> AsyncContextManager:
        # 实现事务逻辑
    
    async def close(self):
        # 关闭连接
```

3. **注册工厂**：在 `infra/database/factory.py` 中添加分支

```bash
def create_database_client(config: DatabaseConfig) -> DatabaseClient:
    if config.type == "postgres":
        return PostgresClient(config)
    elif config.type == "mysql":
        return MySqlClient(config)
    elif config.type == "mongodb":
        return MongoClient(config)
    elif config.type == "my_database":
        return MyDatabaseClient(config)  # 添加新分支
    else:
        raise ValueError(f"Unknown database type: {config.type}")
```

4. **添加配置**：在配置文件中添加新数据库类型的配置项

```yaml
database:
  type: my_database
  # 新数据库的特定配置
```

---

### 添加新的 LLM 提供商

**步骤**：

1. **创建实现文件**：`infra/llm/providers/my_provider.py`

2. **实现接口**：
```bash
from infra.llm.base import LLMClient
from infra.llm.schemas import Message, ChatResponse

class MyProviderClient(LLMClient):
    def __init__(self, config: MyProviderConfig):
        self.config = config
        self.client = MyProviderSDK(api_key=config.api_key)
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        # 转换消息格式
        formatted_messages = self._format_messages(messages)
        # 调用 SDK
        response = await self.client.chat(formatted_messages)
        # 转换响应格式
        return ChatResponse(
            content=response.content,
            usage=response.usage
        )
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        # 实现向量化逻辑
```

3. **注册工厂**：在 `infra/llm/factory.py` 中添加分支

```bash
def create_llm_client(config: LLMConfig) -> LLMClient:
    if config.provider == "openai":
        return OpenAIClient(config)
    elif config.provider == "anthropic":
        return AnthropicClient(config)
    elif config.provider == "my_provider":
        return MyProviderClient(config)  # 添加新分支
    else:
        raise ValueError(f"Unknown provider: {config.provider}")
```

---

## 📁 文件结构

```
infra/
├── __init__.py
├── database/
│   ├── __init__.py
│   ├── base.py              # DatabaseClient 接口
│   ├── factory.py           # create_database_client()
│   ├── postgres.py          # PostgreSQL 实现
│   ├── mysql.py             # MySQL 实现
│   ├── mongodb.py           # MongoDB 实现
│   ├── schemas.py           # 数据模型
│   └── examples/           # 使用示例
│       └── basic_usage.py
├── llm/
│   ├── __init__.py
│   ├── base.py              # LLMClient 接口
│   ├── factory.py           # create_llm_client()
│   ├── providers/
│   │   ├── openai.py        # OpenAI 实现
│   │   ├── anthropic.py     # Anthropic 实现
│   │   ├── deepseek.py      # DeepSeek 实现
│   │   └── mock.py          # Mock 实现
│   ├── schemas.py           # Message, ChatResponse
│   └── examples/
│       └── basic_usage.py
├── vector/
│   ├── __init__.py
│   ├── base.py              # VectorStore 接口
│   ├── factory.py           # create_vector_store()
│   ├── milvus.py            # Milvus 实现
│   ├── faiss.py             # FAISS 实现
│   ├── pinecone.py          # Pinecone 实现
│   ├── schemas.py           # Vector, SearchResult
│   └── examples/
│       └── basic_usage.py
├── cache/
│   ├── __init__.py
│   ├── base.py              # CacheClient 接口
│   ├── factory.py           # create_cache_client()
│   ├── redis_client.py      # Redis 实现
│   ├── memory_cache.py      # 内存缓存实现
│   └── schemas.py           # 缓存数据模型
├── config/
│   ├── __init__.py
│   ├── loader.py            # load_config()
│   ├── schemas.py           # Config 数据模型
│   └── examples/
│       └── config_example.yaml
├── logging/
│   ├── __init__.py
│   ├── logger.py            # 结构化日志
│   └── formatters.py        # 日志格式化
├── monitoring/
│   ├── __init__.py
│   ├── metrics.py           # 指标采集
│   └── health.py            # 健康检查
├── di/
│   ├── __init__.py
│   └── container.py         # DIContainer
└── utils/
    ├── __init__.py
    └── helpers.py           # 通用工具函数
```

---

## 🏗️ 架构设计

### 三层架构

基础设施层采用三层架构设计：

**接口层（base.py）**：
- 定义抽象接口
- 定义数据模型
- 不依赖具体实现

**实现层（postgres.py, openai.py 等）**：
- 提供具体实现
- 依赖第三方库
- 实现接口方法

**工厂层（factory.py）**：
- 提供工厂函数
- 根据配置创建实例
- 隐藏创建复杂度

---

### 设计模式

#### 1. 接口与实现分离

**实现方式**：
- 接口定义在 `base.py` 文件中
- 实现定义在具体文件中（如 `postgres.py`）
- 通过接口引用实例，而不是具体实现类

**优势**：
- 易于切换实现，只需修改配置
- 易于测试，可以 Mock 接口
- 易于扩展，添加新实现不影响现有代码

---

#### 2. 工厂模式

**实现方式**：
- 工厂函数根据配置返回合适的实现
- 隐藏创建复杂度，简化使用
- 统一管理实例生命周期

**优势**：
- 配置驱动创建实例
- 隐藏创建复杂度
- 易于管理实例生命周期
- 支持依赖注入

---

#### 3. 配置驱动

**实现方式**：
- 所有模块通过配置初始化
- 配置文件定义类型和参数
- 环境变量可以覆盖配置文件

**优势**：
- 切换实现只需修改配置
- 支持多环境部署
- 配置集中管理
- 易于运维

---

#### 4. 依赖注入

**实现方式**：
- 使用 DI 容器管理依赖
- 基础设施层注册基础服务
- 上层通过容器获取服务实例

**优势**：
- 解耦组件依赖
- 易于测试
- 统一管理服务生命周期
- 支持延迟加载

---

## 🚀 快速开始

### 5 分钟上手

**步骤 1：加载配置**
```bash
from infra.config import load_config

config = load_config("config/infra/development.yaml")
```

**步骤 2：创建数据库客户端**
```bash
from infra.database import create_database_client

db = create_database_client(config.database)
result = await db.execute("SELECT * FROM users LIMIT 10")
```

**步骤 3：创建 LLM 客户端**
```bash
from infra.llm import create_llm_client

llm = create_llm_client(config.llm)
response = await llm.chat([{"role": "user", "content": "你好"}])
```

**步骤 4：创建向量存储**
```bash
from infra.vector import create_vector_store

vector_store = create_vector_store(config.vector)
ids = await vector_store.add([Vector(values=[0.1, ...])])
```

---

## 🛠️ 开发与部署

### 开发规范

| 文档 | 说明 |
|------|------|
| [开发规范](guides/DEVELOPMENT.md) | 代码规范、接口设计、配置驱动、测试规范 |
| [部署指南](guides/DEPLOYMENT.md) | 部署架构、数据库部署、消息队列、监控配置 |

### 系统级规范

| 文档 | 说明 |
|------|------|
| [系统级开发规范](../../docs/guides/DEVELOPMENT.md) | 提交规范、分支策略、PR流程、代码审查 |
| [系统级部署指南](../../docs/guides/DEPLOYMENT.md) | 环境管理、CI/CD、监控告警、故障排查 |
| [系统级测试指南](../../docs/TESTING_GUIDE.md) | 测试策略、测试类型、覆盖率要求 |

---

## 🔗 Management 系统集成

### 管理接口说明

aiPlat-infra 的管理模块提供统一的管理接口，可被 **aiPlat-management** 系统调用。

**架构关系**：
```
┌─────────────────────────────────────────┐
│      aiPlat-management (独立系统)       │
│    监控、诊断、配置、告警                │
└────────────┬────────────────────────────┘
             │ 调用管理接口
             ▼
┌─────────────────────────────────────────┐
│         aiPlat-infra (Layer 0)          │
│  ┌───────────────────────────────────┐  │
│  │    Management Module               │  │
│  │  - get_status()    状态获取         │  │
│  │  - get_metrics()   指标采集         │  │
│  │  - health_check()  健康检查         │  │
│  │  - get_config()    配置获取         │  │
│  │  - diagnose()      故障诊断         │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### 管理接口调用示例

```python
# aiPlat-management 调用 aiPlat-infra 的管理接口

from aiPlat_infra.management import InfraManager

# 获取 infra 层状态
manager = InfraManager()
status = await manager.get_status()
# 返回：{"status": "healthy", "uptime": 86400, ...}

# 获取指标
metrics = await manager.get_metrics()
# 返回：{"database": {"connections": 10}, "cache": {"hit_rate": 0.95}, ...}

# 健康检查
health = await manager.health_check()
# 返回：{"healthy": true, "checks": [...]}

# 故障诊断
diagnosis = await manager.diagnose()
# 返回：{"issues": [], "recommendations": []}
```

### 详细文档

- **管理模块文档**：[management/index.md](management/index.md)
- **Management 系统**：[aiPlat-management 文档](../aiPlat-management/docs/index.md)

---

## 🔗 相关链接

### 上下层文档
- **上级**：[← 返回主文档](../../docs/index.md)
- **下级模块**：[database](database/index.md) | [llm](llm/index.md) | [vector](vector/index.md)

### 同级文档
- [infra (当前位置)](index.md)
- [core →](../aiPlat-core/docs/index.md)
- [platform →](../aiPlat-platform/docs/index.md)
- [app →](../aiPlat-app/docs/index.md)
- [management →](../aiPlat-management/docs/index.md) ---

*最后更新: 2026-04-10*