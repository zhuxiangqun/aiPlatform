# 👨‍💻 基础设施层开发者指南（As-Is 对齐 + To-Be 示例）

> 说明：本文档中的 make/docker/config 示例可能依赖外部 ops 仓库；As-Is 以当前 infra 代码与 tests 为准。

> aiPlat-infra - 开发指南与最佳实践

---

## 🎯 开发者关注点

作为基础设施层开发者，您需要了解：
- **如何使用**：如何调用基础设施服务
- **如何扩展**：如何添加新的数据库、LLM、向量存储实现
- **如何测试**：如何编写单元测试和集成测试
- **最佳实践**：开发中的最佳实践

---

## 🛠️ 开发环境搭建

### 前置条件

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Python | 3.10+ | 后端开发 |
| Docker | 20.10+ | 本地服务 |
| Make | 3.81+ | 构建脚本 |

### 本地服务启动

**启动依赖服务**：
```bash
# To-Be：启动 PostgreSQL、Redis、Milvus（需提供 compose/make）
# make docker-up-infra

# 等待服务就绪
make docker-wait

# 查看服务状态
make docker-status
```

**配置环境变量**：
```bash
# 复制配置模板
cp config/infra/database.yaml.example config/infra/database.yaml
cp config/infra/llm.yaml.example config/infra/llm.yaml
cp config/infra/vector.yaml.example config/infra/vector.yaml

# 编辑配置文件，填入必要的配置
# - 数据库连接字符串
# - LLM API 密钥
# - 向量存储配置
```

### 验证环境

**测试服务连接**：
```bash
# 测试数据库连接
make test-db

# 测试 Redis 连接
make test-redis

# 测试向量存储（To-Be）
# make test-vector

# 测试 LLM 连接
make test-llm
```

---

## 🚀 快速开始

### 5 分钟跑起来

**步骤一：安装依赖**
```bash
cd aiPlat-infra
pip install -e .
```

**步骤二：配置服务**
```bash
# 编辑配置文件，设置数据库连接
vi config/infra/database.yaml
```

**步骤三：测试连接**
```bash
make test-infra
```

---

## 📁 项目目录结构

```
aiPlat-infra/
├── __init__.py
│
├── compute/                      # 算力管理
│   ├── __init__.py
│   ├── base.py                   # ComputeManager 接口
│   ├── factory.py                # create_compute_manager()
│   ├── kubernetes.py             # K8s 实现
│   ├── docker.py                 # Docker 实现
│   └── schemas.py                # 数据模型
│
├── memory/                       # 内存管理
│   ├── __init__.py
│   ├── base.py                   # MemoryManager 接口
│   ├── factory.py                # create_memory_manager()
│   ├── cache.py                  # 多级缓存实现
│   ├── vram.py                   # 显存管理
│   └── schemas.py                # 数据模型
│
├── storage/                      # 存储管理
│   ├── __init__.py
│   ├── base.py                   # StorageClient 接口
│   ├── factory.py                # create_storage_client()
│   ├── local.py                  # 本地存储
│   ├── s3.py                     # S3 存储
│   └── schemas.py                # 数据模型
│
├── network/                      # 网络管理
│   ├── __init__.py
│   ├── base.py                   # NetworkManager 接口
│   ├── factory.py                # create_network_manager()
│   ├── discovery/                # 服务发现
│   │   ├── consul.py
│   │   └── etcd.py
│   ├── loadbalancer/             # 负载均衡
│   │   ├── nginx.py
│   │   └── envoy.py
│   └── schemas.py
│
├── database/                     # 数据库抽象
│   ├── __init__.py
│   ├── base.py                   # DatabaseClient 接口
│   ├── factory.py                # create_database_client()
│   ├── postgres.py               # PostgreSQL 实现
│   ├── mysql.py                  # MySQL 实现
│   ├── mongodb.py                # MongoDB 实现
│   └── schemas.py                # 数据模型
│
├── llm/                          # LLM 服务
│   ├── __init__.py
│   ├── base.py                   # LLMClient 接口
│   ├── factory.py                # create_llm_client()
│   ├── providers/                # 提供商实现
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   ├── deepseek.py
│   │   └── mock.py
│   ├── schemas.py                # Message, ChatResponse
│   └── examples/
│       └── basic_usage.py
│
├── vector/                       # 向量存储
│   ├── __init__.py
│   ├── base.py                   # VectorStore 接口
│   ├── factory.py                # create_vector_store()
│   ├── milvus.py                 # Milvus 实现
│   ├── faiss.py                  # FAISS 实现
│   ├── pinecone.py               # Pinecone 实现
│   └── schemas.py                # Vector, SearchResult
│
├── messaging/                    # 消息队列
│   ├── __init__.py
│   ├── base.py                   # MessageQueue 接口
│   ├── factory.py                # create_message_queue()
│   ├── kafka.py                  # Kafka 实现
│   ├── rabbitmq.py               # RabbitMQ 实现
│   └── schemas.py
│
├── cache/                        # 缓存
│   ├── __init__.py
│   ├── base.py                   # CacheClient 接口
│   ├── factory.py                # create_cache_client()
│   ├── redis.py                  # Redis 实现
│   ├── memory.py                 # 内存缓存
│   └── schemas.py
│
├── mcp/                          # MCP 协议
│   ├── __init__.py
│   ├── base.py                   # MCPClient 接口
│   ├── factory.py                # create_mcp_client()
│   ├── protocol.py               # JSON-RPC 协议
│   ├── client.py                 # MCP 客户端
│   └── schemas.py
│
├── config/                       # 配置管理
│   ├── __init__.py
│   ├── loader.py                 # load_config()
│   ├── manager.py                # 配置管理
│   └── schemas.py                # 配置数据模型
│
├── logging/                      # 日志系统
│   ├── __init__.py
│   ├── logger.py                 # get_logger()
│   └── formatters.py             # 日志格式化
│
├── monitoring/                   # 监控
│   ├── __init__.py
│   ├── metrics.py                # 指标采集
│   └── health.py                 # 健康检查
│
├── di/                           # 依赖注入
│   ├── __init__.py
│   └── container.py              # DIContainer
│
├── utils/                        # 工具函数
│   ├── __init__.py
│   └── helpers.py                # 通用工具
│
├── examples/                     # 使用示例
│   ├── database_example.py
│   ├── llm_example.py
│   └── vector_example.py
│
└── tests/                        # 测试目录
    ├── unit/
    │   ├── compute/
    │   ├── database/
    │   ├── llm/
    │   └── vector/
    ├── integration/
    └── fixtures/
```

### 目录说明

| 目录 | 职责 | 关键文件 |
|------|------|----------|
| `compute/` | 算力管理 | base.py, factory.py |
| `memory/` | 内存管理 | base.py, factory.py |
| `storage/` | 存储管理 | base.py, factory.py |
| `network/` | 网络管理 | base.py, factory.py |
| `database/` | 数据库抽象 | base.py, factory.py |
| `llm/` | LLM 服务 | base.py, factory.py, providers/ |
| `vector/` | 向量存储 | base.py, factory.py |
| `messaging/` | 消息队列 | base.py, factory.py |
| `cache/` | 缓存 | base.py, factory.py |
| `mcp/` | MCP 协议 | base.py, factory.py |
| `config/` | 配置管理 | loader.py |
| `logging/` | 日志系统 | logger.py |
| `monitoring/` | 监控 | metrics.py, health.py |
| `di/` | 依赖注入 | container.py |
| `utils/` | 工具函数 | helpers.py |
| `tests/` | 测试 | unit/, integration/ |

### 模块文件命名规范

| 文件类型 | 命名规则 | 示例 |
|----------|----------|------|
| 接口定义 | `base.py` | `database/base.py` |
| 工厂函数 | `factory.py` | `database/factory.py` |
| 实现类 | `{backend}.py` | `database/postgres.py` |
| 数据模型 | `schemas.py` | `database/schemas.py` |
| 工具函数 | `utils.py` | `compute/utils.py` |
| 使用示例 | `examples/` | `llm/examples/basic_usage.py` |
| 单元测试 | `tests/unit/{module}/` | `tests/unit/database/test_base.py` |

---

## 📖 核心模块使用

### database - 数据库

**详细文档**：[database 模块文档](../../database/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取数据库实例 | 调用 `create_database_client(config)` | `infra/factories/database.py` |
| 执行查询 | 调用 `client.query(sql, params)` | `infra/database/base.py` |
| 执行事务 | 使用 `async with client.transaction()` | `infra/database/base.py` |
| 批量插入 | 调用 `client.batch_insert(table, data)` | `infra/database/base.py` |

**配置示例**：
```yaml
# config/infra/database.yaml
type: postgresql
host: localhost
port: 5432
database: aiplatform
user: postgres
password: ${DATABASE_PASSWORD}
pool:
  min_size: 5
  max_size: 20
```

**如何添加新的数据库实现**：

1. **创建实现文件**：在 `infra/database/implementations/` 下新建 `mysql_client.py`
2. **实现接口**：继承 `DatabaseClient` 基类，实现所有抽象方法
3. **注册工厂**：在 `create_database_client()` 中添加 `mysql` 类型分支
4. **添加配置**：在 `config/infra/database.yaml.example` 中添加 MySQL 配置示例
5. **编写测试**：在 `tests/unit/infra/database/` 下添加测试文件

**相关文件位置**：
- 接口定义：`infra/database/base.py`
- 工厂函数：`infra/factories/database.py`
- 配置示例：`config/infra/database.yaml.example`
- 测试文件：`tests/unit/infra/database/`

---

### llm - LLM 客户端

**详细文档**：[llm 模块文档](../../llm/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取 LLM 客户端 | 调用 `create_llm_client(config)` | `infra/factories/llm.py` |
| 对话 | 调用 `client.chat(messages)` | `infra/llm/base.py` |
| 流式对话 | 调用 `client.chat_stream(messages)` | `infra/llm/base.py` |
| 嵌入 | 调用 `client.embed(text)` | `infra/llm/base.py` |
| Token 计数 | 调用 `client.count_tokens(text)` | `infra/llm/base.py` |

**配置示例**：
```yaml
# config/infra/llm.yaml
provider: openai
model: gpt-4
api_key: ${LLM_API_KEY}
temperature: 0.7
max_tokens: 4096
timeout: 60
retry:
  max_attempts: 3
  backoff_factor: 2
```

**如何添加新的 LLM 提供商**：

1. **创建实现文件**：在 `infra/llm/providers/` 下新建 `anthropic_client.py`
2. **实现接口**：继承 `LLMClient` 基类，实现 `chat()`, `chat_stream()`, `embed()` 方法
3. **注册工厂**：在 `create_llm_client()` 中添加 `anthropic` 类型分支
4. **添加配置**：在 `config/infra/llm.yaml.example` 中添加 Anthropic 配置示例
5. **编写测试**：在 `tests/unit/infra/llm/` 下添加测试文件

**支持的提供商**：

| 提供商 | 配置类型 | 说明 |
|--------|----------|------|
| OpenAI | `openai` | GPT-4, GPT-3.5 |
| Anthropic | `anthropic` | Claude系列 |
| DeepSeek | `deepseek` | DeepSeek Chat |
| 本地模型 | `local` | Ollama, vLLM |
| Mock | `mock` | 用于测试 |

**相关文件位置**：
- 接口定义：`infra/llm/base.py`
- 工厂函数：`infra/factories/llm.py`
- 配置示例：`config/infra/llm.yaml.example`
- 测试文件：`tests/unit/infra/llm/`

---

### vector - 向量数据库

**详细文档**：[vector 模块文档](../../vector/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取向量存储 | 调用 `create_vector_store(config)` | `infra/factories/vector.py` |
| 添加向量 | 调用 `store.add(ids, vectors, metadata)` | `infra/vector/base.py` |
| 搜索向量 | 调用 `store.search(query_vector, top_k)` | `infra/vector/base.py` |
| 删除向量 | 调用 `store.delete(ids)` | `infra/vector/base.py` |
| 创建索引 | 调用 `store.create_index(dimension)` | `infra/vector/base.py` |

**配置示例**：
```yaml
# config/infra/vector.yaml
type: milvus
host: localhost
port: 19530
collection: aiplatform_vectors
dimension: 1536
index_type: IVF_FLAT
metric_type: L2
```

**如何添加新的向量存储实现**：

1. **创建实现文件**：在 `infra/vector/implementations/` 下新建 `pinecone_client.py`
2. **实现接口**：继承 `VectorStore` 基类，实现所有抽象方法
3. **注册工厂**：在 `create_vector_store()` 中添加 `pinecone` 类型分支
4. **添加配置**：在 `config/infra/vector.yaml.example` 中添加 Pinecone 配置示例
5. **编写测试**：在 `tests/unit/infra/vector/` 下添加测试文件

**相关文件位置**：
- 接口定义：`infra/vector/base.py`
- 工厂函数：`infra/factories/vector.py`
- 配置示例：`config/infra/vector.yaml.example`
- 测试文件：`tests/unit/infra/vector/`

---

### config - 配置管理

**详细文档**：[config 模块文档](../../config/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 加载配置 | 调用 `load_config(path)` | `infra/config/loader.py` |
| 获取配置值 | 调用 `config.get(key, default)` | `infra/config/manager.py` |
| 环境变量 | 使用 `${ENV_VAR}` 语法 | `infra/config/loader.py` |
| 多环境 | 使用 `config/{env}/` 目录 | `infra/config/loader.py` |

**配置加载顺序**：
1. 默认配置文件
2. 环境特定配置文件
3. 环境变量覆盖
4. 命令行参数覆盖

**相关文件位置**：
- 配置加载：`infra/config/loader.py`
- 配置管理：`infra/config/manager.py`
- 配置示例：`config/infra/`

---

### logging - 日志系统

**详细文档**：[logging 模块文档](../../logging/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取日志器 | 调用 `get_logger(name)` | `infra/logging/logger.py` |
| 记录日志 | 调用 `logger.info()`, `logger.error()` 等 | `infra/logging/logger.py` |
| 结构化日志 | 传入 `extra` 参数 | `infra/logging/logger.py` |
| 配置日志 | 编辑 `config/infra/logging.yaml` | `config/infra/logging.yaml` |

**日志级别**：
- DEBUG：详细调试信息
- INFO：关键操作信息
- WARNING：警告信息
- ERROR：错误信息
- CRITICAL：严重错误

**相关文件位置**：
- 日志器：`infra/logging/logger.py`
- 配置：`config/infra/logging.yaml`

---

### compute - 算力管理

**详细文档**：[compute 模块文档](../../compute/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取计算管理器 | 调用 `create_compute_manager(config)` | `infra/compute/factory.py` |
| 分配资源 | 调用 `manager.allocate(request)` | `infra/compute/base.py` |
| 释放资源 | 调用 `manager.release(allocation_id)` | `infra/compute/base.py` |
| 提交任务 | 调用 `manager.submit_task(task)` | `infra/compute/base.py` |

**配置示例**：
```yaml
# config/infra/compute.yaml
backend: kubernetes  # kubernetes, docker, baremetal
scheduling:
  policy: fair_share
  preemption: true
default_quota:
  cpu: 8
  gpu: 2
  memory: 32Gi
```

**相关文件位置**：
- 接口定义：`infra/compute/base.py`
- 工厂函数：`infra/compute/factory.py`
- K8s 实现：`infra/compute/kubernetes/`

---

### memory - 内存管理

**详细文档**：[memory 模块文档](../../memory/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取内存管理器 | 调用 `create_memory_manager(config)` | `infra/memory/factory.py` |
| 分配内存 | 调用 `manager.allocate(request)` | `infra/memory/base.py` |
| 释放内存 | 调用 `manager.release(allocation_id)` | `infra/memory/base.py` |
| 获取统计 | 调用 `manager.get_stats(node_id)` | `infra/memory/base.py` |

**配置示例**：
```yaml
# config/infra/memory.yaml
ram:
  enabled: true
  pool_enabled: true
  pool_size: 8Gi
  oom_threshold: 0.9
vram:
  enabled: true
  backend: cuda
  pool_enabled: true
  pool_size: 16Gi
```

**相关文件位置**：
- 接口定义：`infra/memory/base.py`
- 工厂函数：`infra/memory/factory.py`
- VRAM 实现：`infra/memory/vram/`

---

### network - 网络管理

**详细文档**：[network 模块文档](../../network/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取网络管理器 | 调用 `create_network_manager(config)` | `infra/network/factory.py` |
| 注册服务 | 调用 `manager.register_service(service)` | `infra/network/base.py` |
| 服务发现 | 调用 `manager.discover_services(name)` | `infra/network/base.py` |
| 获取负载均衡 | 调用 `manager.get_load_balancer(name)` | `infra/network/base.py` |

**配置示例**：
```yaml
# config/infra/network.yaml
discovery:
  backend: consul
  address: localhost:8500
load_balancer:
  algorithm: weighted
  connection_timeout: 5
health_check:
  enabled: true
  interval: 10
```

**相关文件位置**：
- 接口定义：`infra/network/base.py`
- 工厂函数：`infra/network/factory.py`
- 服务发现实现：`infra/network/discovery/`

---

### mcp - MCP 协议

**详细文档**：[mcp 模块文档](../../mcp/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取 MCP 客户端 | 调用 `create_mcp_client(config)` | `infra/mcp/factory.py` |
| 连接 | 调用 `await client.connect()` | `infra/mcp/base.py` |
| 列出工具 | 调用 `await client.list_tools()` | `infra/mcp/base.py` |
| 调用工具 | 调用 `await client.call_tool(name, args)` | `infra/mcp/base.py` |

**配置示例**：
```yaml
# config/infra/mcp.yaml
mcp:
  timeout: 30
  max_retries: 3
  servers:
    - name: filesystem
      type: stdio
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "./data"]
    - name: brave-search
      type: http
      url: http://localhost:3001/mcp
```

**相关文件位置**：
- 接口定义：`infra/mcp/base.py`
- 工厂函数：`infra/mcp/factory.py`
- 协议实现：`infra/mcp/protocol/`

---

## 🔧 如何扩展

### 添加新模块

**步骤**：

1. **创建模块目录**：在 `infra/` 下创建新模块目录
2. **定义接口**：创建 `base.py` 定义抽象接口
3. **实现默认实现**：创建 `implementations/` 目录存放具体实现
4. **创建工厂函数**：在 `infra/factories/` 下创建工厂函数
5. **添加配置示例**：在 `config/infra/` 下添加配置示例
6. **编写测试**：在 `tests/unit/infra/` 下编写测试
7. **更新文档**：更新模块文档和索引

### 模块结构模板

```
infra/{module_name}/
├── __init__.py          # 模块入口
├── base.py              # 抽象接口定义
├── implementations/    # 具体实现
│   ├── __init__.py
│   ├── impl_a.py
│   └── impl_b.py
└── utils.py             # 工具函数

infra/factories/
└── {module_name}.py     # 工厂函数

config/infra/
└── {module_name}.yaml.example  # 配置示例

tests/unit/infra/{module_name}/
├── __init__.py
├── test_base.py
└── test_implementations.py
```

---

## 🧪 测试

### 测试目录结构

```
tests/
├── unit/infra/              # 单元测试
│   ├── database/
│   │   ├── test_base.py
│   │   └── test_implementations.py
│   ├── llm/
│   │   ├── test_base.py
│   │   └── test_providers.py
│   └── vector/
│       └── test_base.py
├── integration/infra/       # 集成测试
│   ├── test_database_integration.py
│   ├── test_llm_integration.py
│   └── test_vector_integration.py
└── fixtures/                # 测试数据
    └── infra/
        ├── sample_data.json
        └── test_configs.yaml
```

### 运行测试

| 命令 | 用途 | 前置条件 |
|------|------|----------|
| `make test-infra-unit` | 运行基础设施层单元测试 | 无 |
| `make test-infra-integration` | 运行基础设施层集成测试 | Docker 服务启动 |
| `make test-infra-all` | 运行基础设施层所有测试 | Docker 服务启动 |
| `make test-infra-coverage` | 生成覆盖率报告 | 无 |

### 测试编写规范

| 规范 | 说明 |
|------|------|
| 测试文件命名 | `test_{模块名}.py` |
| 测试类命名 | `Test{功能名}` |
| 测试函数命名 | `test_{功能}_{场景}` |
| Mock 使用 | 使用 `conftest.py` 提供公共 fixture |
| 集成测试标记 | 使用 `@pytest.mark.integration` |

### Mock 示例

**测试 fixture**（在 `conftest.py` 中定义）：
- `mock_database`：模拟数据库客户端
- `mock_llm_client`：模拟 LLM 客户端
- `mock_vector_store`：模拟向量存储
- `test_config`：测试配置对象

---

## 📋 最佳实践

### 1. 使用类型注解

**要求**：所有公开函数必须有参数类型和返回值类型注解

**检查方式**：CI 运行 `mypy` 检查

**正确做法**：
- 接口方法标注参数和返回值类型
- 使用 `Optional` 表示可选参数
- 使用 `Union` 表示多种类型

---

### 2. 使用配置管理

**要求**：不允许硬编码任何配置值

**检查方式**：代码审查 + 定期扫描

**正确做法**：
- 所有配置从配置对象读取
- 敏感信息使用环境变量覆盖
- 配置文件放在 `config/infra/` 目录

---

### 3. 使用依赖注入

**要求**：服务实例通过工厂函数获取，不在函数内部创建

**检查方式**：代码审查

**正确做法**：
- 通过工厂函数获取实例：`db = create_database_client(config)`
- 在应用启动时创建实例，传递给需要的地方

---

### 4. 异常处理

**要求**：捕获具体异常，使用预定义的错误类型

**检查方式**：代码审查

**错误类型**：
- `InfraDBError`：数据库错误
- `InfraLLMError`：LLM 错误
- `InfraVectorError`：向量存储错误
- `InfraConfigError`：配置错误

---

### 5. 资源管理

**要求**：使用上下文管理器管理资源

**检查方式**：代码审查

**正确做法**：
- 数据库连接使用 `async with`
- 文件操作使用 `async with`
- 确保资源正确释放

---

## 🔧 常见问题排查

### 数据库问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 连接超时 | 服务未启动或配置错误 | 1. 执行 `make docker-up-infra`<br>2. 检查配置文件中的连接字符串 |
| 查询慢 | 缺少索引或查询优化 | 1. 检查查询语句<br>2. 添加必要的索引 |
| 连接池耗尽 | 并发连接过多 | 1. 检查连接池配置<br>2. 增加 `pool.max_size` |
| 事务死锁 | 并发更新冲突 | 1. 检查事务顺序<br>2. 减少事务持有时间 |

### LLM 问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| API 调用失败 | API 密钥无效或网络问题 | 1. 检查 `LLM_API_KEY` 环境变量<br>2. 执行 `make test-llm`<br>3. 检查网络代理设置 |
| 响应超时 | 超时设置过短 | 1. 增加 `timeout` 配置<br>2. 减少输入长度 |
| Token 限制 | 输入超出限制 | 1. 减少 `max_tokens` 输出限制<br>2. 使用支持更长上下文的模型 |
| 响应解析失败 | 响应格式不正确 | 1. 检查响应格式<br>2. 添加错误处理 |

### 向量存储问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 连接失败 | 服务未启动 | 1. 执行 `make docker-up-infra`<br>2. 检查 Milvus 端口 |
| 搜索无结果 | 索引为空或维度不匹配 | 1. 检查索引是否创建<br>2. 检查向量维度是否匹配 |
| 插入失败 | ID 重复或数据格式错误 | 1. 检查 ID 是否唯一<br>2. 检查向量维度 |
| 性能差 | 索引类型不合适 | 1. 检查索引类型配置<br>2. 考虑使用更高效的索引类型 |

### 配置问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 配置不生效 | 配置优先级问题 | 1. 检查配置加载顺序<br>2. 确认环境变量是否正确 |
| 环境变量未生效 | 语法错误或作用域问题 | 1. 检查 `${ENV_VAR}` 语法<br>2. 确认环境变量已设置 |
| 配置文件找不到 | 路径错误 | 1. 检查配置文件路径<br>2. 使用绝对路径 |

---

## 📖 相关链接

- [← 返回 infra 主文档](../../index.md)
- [架构师指南 →](../architect/index.md)
- [运维指南 →](../ops/index.md)

---

*最后更新: 2026-04-10*
