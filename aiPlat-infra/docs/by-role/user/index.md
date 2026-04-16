# aiPlat-infra 用户指南（To-Be 为主，As-Is 以代码事实为准）

> 说明：本文档面向“配置/管理基础设施服务”的用户，包含较多脚本与部署相关示例；As-Is 请以 infra 实际提供的配置加载与 tests 为准。

> 本文档面向配置和管理基础设施服务的运维人员和开发者，提供服务配置、连接管理和健康检查指南。

---

## 该文档包含

- 数据库、LLM、向量存储等服务的配置方法
- 服务连接验证和健康检查命令
- 配置参数说明和最佳实践
- 常见问题和故障排查

---

## 快速开始

### 前提条件

在配置基础设施服务之前，确保：
- 已完成基础设施部署（参考 [运维指南](./ops/index.md)）
- 已确认各服务容器/进程正在运行
- 已获取必要的访问凭证（用户名、密码、API Key 等）

### 验证服务状态

**检查所有基础设施服务状态**：
```bash
# 通过本地脚本检查
./scripts/health-check.sh  # To-Be：若 scripts 不在本仓库，请以实际 ops 仓库为准

# 预期输出
[OK] Database: healthy
[OK] LLM Service: healthy
[OK] Vector Store: healthy
[OK] Cache: healthy
```

**检查单个服务状态**：
```bash
# 数据库
curl http://localhost:8000/api/v1/infra/health/database
# 返回: {"status": "healthy", "latency_ms": 5}

# LLM 服务
curl http://localhost:8000/api/v1/infra/health/llm
# 返回: {"status": "healthy", "available_models": ["gpt-4", "claude-3"]}

# 向量存储
curl http://localhost:8000/api/v1/infra/health/vector-store
# 返回: {"status": "healthy", "collections": 5}
```

---

## 数据库服务

### 支持的数据库类型

| 类型 | 用途 | 默认端口 |
|------|------|----------|
| PostgreSQL | 主数据库 | 5432 |
| MySQL | 主数据库（备选） | 3306 |
| MongoDB | 文档存储 | 27017 |
| Redis | 缓存和会话 | 6379 |

### PostgreSQL 配置

**配置文件位置**：
```yaml
# config/services/database.yaml
database:
  type: postgresql
  host: ${DB_HOST:-localhost}
  port: ${DB_PORT:-5432}
  name: ${DB_NAME:-aiplatform}
  user: ${DB_USER:-postgres}
  password: ${DB_PASSWORD:-}
  
  pool:
    min_size: 5
    max_size: 20
    max_overflow: 10
    pool_timeout: 30
    recycle: 3600
    
  ssl:
    enabled: true
    cert_path: /etc/ssl/certs/db-cert.pem
    
  performance:
    statement_timeout: 30000
    lock_timeout: 10000
```

**环境变量配置**：
```bash
# .env
DB_HOST=db.internal.example.com
DB_PORT=5432
DB_NAME=aiplatform
DB_USER=app_user
DB_PASSWORD=secure_password
```

**连接测试**：
```bash
# 通过 psql 客户端测试
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT 1"

# 通过 API 测试
curl -X POST http://localhost:8000/api/v1/infra/database/test-connection \
  -H "Authorization: Bearer <token>" \
  -d '{"host": "db.example.com", "port": 5432, "database": "test"}'
# 返回: {"connected": true, "latency_ms": 12}
```

**性能监控**：
```bash
# 查看连接池状态
curl http://localhost:8000/api/v1/infra/database/pool-status
# 返回:
{
  "pool_size": 15,
  "checked_out": 8,
  "overflow": 0,
  "checked_in": 7
}

# 查看慢查询（超过 1 秒）
curl http://localhost:8000/api/v1/infra/database/slow-queries
```

### MongoDB 配置

**配置文件示例**：
```yaml
# config/services/database.yaml
database:
  type: mongodb
  uri: ${MONGODB_URI:-mongodb://localhost:27017}
  database: ${MONGODB_DB:-aiplatform}
  
  options:
    max_pool_size: 100
    min_pool_size: 10
    max_idle_time_ms: 60000
    connect_timeout_ms: 10000
    socket_timeout_ms: 5000
    
  replica_set:
    enabled: false
    name: rs0
    read_preference: secondaryPreferred
```

**连接测试**：
```bash
# 通过 mongosh 测试
mongosh "$MONGODB_URI" --eval "db.runCommand({ping:1})"

# 通过 API 测试
curl -X POST http://localhost:8000/api/v1/infra/database/test-connection \
  -d '{"type": "mongodb", "uri": "mongodb://localhost:27017"}'
```

### Redis 配置

**配置文件示例**：
```yaml
# config/services/cache.yaml
cache:
  type: redis
  host: ${REDIS_HOST:-localhost}
  port: ${REDIS_PORT:-6379}
  password: ${REDIS_PASSWORD:-}
  db: ${REDIS_DB:-0}
  
  pool:
    max_connections: 50
    retry_on_timeout: true
    
  ssl:
    enabled: true
    
  memory:
    max_memory: 4gb
    eviction_policy: allkeys-lru
```

**连接测试**：
```bash
# 通过 redis-cli 测试
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# 通过 API 测试
curl -X POST http://localhost:8000/api/v1/infra/cache/test-connection
# 返回: {"connected": true, "latency_ms": 2}
```

---

## LLM 服务

### 支持的 LLM 提供商

| 提供商 | 模型示例 | 特点 |
|--------|----------|------|
| OpenAI | gpt-4, gpt-3.5-turbo | 通用性强，响应快 |
| Anthropic | claude-3-opus, claude-3-sonnet | 长上下文，推理强 |
| 本地部署 | llama2, mistral | 私有化，成本低 |

### OpenAI 配置

**配置文件示例**：
```yaml
# config/services/llm.yaml
llm:
  providers:
    - name: openai
      type: openai
      api_key: ${OPENAI_API_KEY}
      base_url: ${OPENAI_BASE_URL:-https://api.openai.com/v1}
      
      models:
        - name: gpt-4
          context_window: 8192
          max_tokens: 4096
          temperature: 0.7
          cost_per_1k_tokens:
            input: 0.03
            output: 0.06
            
        - name: gpt-3.5-turbo
          context_window: 4096
          max_tokens: 2048
          temperature: 0.7
          
      rate_limit:
        requests_per_minute: 60
        tokens_per_minute: 90000
        
      retry:
        max_attempts: 3
        backoff_factor: 2
```

**连接测试**：
```bash
# 测试 API Key 有效性
curl -X POST http://localhost:8000/api/v1/infra/llm/test-connection \
  -H "Authorization: Bearer <token>" \
  -d '{"provider": "openai"}'
# 返回: {"connected": true, "available_models": ["gpt-4", "gpt-3.5-turbo"]}

# 测试模型调用
curl -X POST http://localhost:8000/api/v1/infra/llm/test-completion \
  -d '{
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "prompt": "Hello, test",
    "max_tokens": 50
  }'
# 返回: {"completion": "Hello! How can I assist you?", "latency_ms": 450}
```

### Anthropic 配置

**配置文件示例**：
```yaml
# config/services/llm.yaml
llm:
  providers:
    - name: anthropic
      type: anthropic
      api_key: ${ANTHROPIC_API_KEY}
      
      models:
        - name: claude-3-opus
          context_window: 200000
          max_tokens: 4096
          temperature: 0.7
          
        - name: claude-3-sonnet
          context_window: 200000
          max_tokens: 4096
          temperature: 0.7
```

### 本地模型配置

**配置文件示例**：
```yaml
# config/services/llm.yaml
llm:
  providers:
    - name: local_llama
      type: local
      model_path: /models/llama2-7b
      device: cuda:0
      
      models:
        - name: llama2-7b
          context_window: 4096
          max_tokens: 2048
          temperature: 0.7
          
      performance:
        batch_size: 32
        max_queue_size: 100
```

### 嵌入服务配置

**配置文件示例**：
```yaml
# config/services/llm.yaml
embedding:
  providers:
    - name: openai_embedding
      type: openai
      model: text-embedding-3-large
      dimension: 3072
      
    - name: local_embedding
      type: local
      model_path: /models/all-MiniLM-L6-v2
      dimension: 384
```

**测试嵌入服务**：
```bash
curl -X POST http://localhost:8000/api/v1/infra/embedding/test \
  -d '{"provider": "openai_embedding", "text": "Hello world"}'
# 返回: {"embedding": [...], "dimension": 3072, "latency_ms": 120}
```

---

## 向量存储服务

### 支持的向量存储

| 存储类型 | 特点 | 适用场景 |
|----------|------|----------|
| Milvus | 分布式，高性能 | 大规模向量检索 |
| Qdrant | 轻量级，易部署 | 中小规模应用 |
| Pinecone | 托管服务 | 无运维需求 |
| pgvector | PostgreSQL 扩展 | 已使用 PG 的场景 |

### Milvus 配置

**配置文件示例**：
```yaml
# 配置文件位置: config/services/vector-store.yaml
vector_store:
  type: milvus
  host: ${MILVUS_HOST:-localhost}
  port: ${MILVUS_PORT:-19530}
  
  collections:
    - name: knowledge_vectors
      dimension: 3072
      metric: cosine
      index_type: HNSW
      
      hnsw_config:
        m: 16
        ef_construction: 256
        
    - name: memory_vectors
      dimension: 1536
      metric: ip
      index_type: IVF_FLAT
      
  performance:
    search_timeout: 10
    insert_batch_size: 1000
    replica_number: 2
```

**连接测试**：
```bash
# 测试 Milvus 连接
curl -X POST http://localhost:8000/api/v1/infra/vector-store/test-connection \
  -d '{"host": "localhost", "port": 19530}'
# 返回: {"connected": true, "collections": ["knowledge_vectors", "memory_vectors"]}

# 测试向量插入和检索
curl -X POST http://localhost:8000/api/v1/infra/vector-store/test-search \
  -d '{
    "collection": "knowledge_vectors",
    "vector": [0.1, 0.2, ...],
    "top_k": 5
  }'
# 返回: {"results": [...], "latency_ms": 25}
```

### Qdrant 配置

**配置文件示例**：
```yaml
# config/services/vector-store.yaml
vector_store:
  type: qdrant
  host: ${QDRANT_HOST:-localhost}
  port: ${QDRANT_PORT:-6333}
  grpc_port: 6334
  
  collections:
    - name: documents
      vector_size: 1536
      distance: Cosine
      
      config:
        hnsw_config:
          m: 16
          ef_construct: 100
```

### pgvector 配置（使用 PostgreSQL）

**配置文件示例**：
```yaml
# config/services/vector-store.yaml
vector_store:
  type: pgvector
  connection:
    host: ${DB_HOST:-localhost}
    port: 5432
    database: ${DB_NAME:-aiplatform}
    user: ${DB_USER:-postgres}
    password: ${DB_PASSWORD:-}
    
  tables:
    - name: document_embeddings
      dimensions: 1536
      
  indexes:
    type: hnsw
    m: 16
    ef_construction: 64
```

**初始化 pgvector 扩展**：
```bash
# 在 PostgreSQL 中执行
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

---

## 配置管理服务

### 配置源优先级

系统按以下优先级加载配置（高优先级覆盖低优先级）：

1. **命令行参数**（最高）
2. **环境变量**
3. **配置文件**
4. **默认值**（最低）

### 配置文件结构

**主配置文件**：`config/config.yaml`
```yaml
# config/config.yaml
environment: ${ENV:-development}

services:
  database: config/services/database.yaml
  llm: config/services/llm.yaml
  vector_store: config/services/vector-store.yaml
  cache: config/services/cache.yaml

logging:
  level: ${LOG_LEVEL:-INFO}
  format: json
  
monitoring:
  enabled: true
  port: 9090
```

### 环境变量覆盖

**配置环境变量**：
```bash
# .env 或直接设置
export ENV=production
export DB_HOST=db.prod.example.com
export DB_PORT=5432
export DB_USER=app_user
export DB_PASSWORD=secure_password
export OPENAI_API_KEY=sk-...
export REDIS_HOST=redis.prod.example.com
export LOG_LEVEL=DEBUG
```

### 动态配置更新

**运行时配置更新**：
```bash
# 重新加载配置（不重启服务）
curl -X POST http://localhost:8000/api/v1/infra/config/reload \
  -H "Authorization: Bearer <token>"

# 更新单个配置项
curl -X PATCH http://localhost:8000/api/v1/infra/config \
  -d '{"LOG_LEVEL": "WARNING"}'
```

---

## 常见问题

### 数据库连接失败

**症状**：无法连接到数据库，超时或拒绝连接。

**排查步骤**：

1. **检查网络连通性**：
```bash
# 测试端口连通
telnet $DB_HOST $DB_PORT
# 或
nc -zv $DB_HOST $DB_PORT
```

2. **检查认证信息**：
```bash
# 验证用户名密码
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"
```

3. **检查防火墙规则**：
```bash
# 查看服务日志
docker logs postgres-container
# 或
journalctl -u postgresql
```

4. **检查连接池状态**：
```bash
curl http://localhost:8000/api/v1/infra/database/pool-status
```

**常见原因和解决方法**：

| 原因 | 解决方法 |
|------|----------|
| 主机名错误 | 检查环境变量 `$DB_HOST` |
| 端口错误 | 检查环境变量 `$DB_PORT` |
| 认证失败 | 检查用户名和密码 |
| 防火墙阻断 | 配置防火墙规则 |
| 连接池耗尽 | 增加 `max_size` 配置 |
| SSL 配置错误 | 检查证书路径和配置 |

### LLM 调用失败

**症状**：API 调用返回错误或超时。

**排查步骤**：

1. **检查 API Key**：
```bash
# 测试 OpenAI API Key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 预期返回模型列表
```

2. **检查配额和速率限制**：
```bash
curl http://localhost:8000/api/v1/infra/llm/rate-limit-status \
  -d '{"provider": "openai"}'
# 返回: {"requests_used": 450, "requests_limit": 1000}
```

3. **检查网络连通性**：
```bash
curl -I https://api.openai.com
```

4. **查看 LLM 服务日志**：
```bash
curl http://localhost:8000/api/v1/infra/logs/llm?level=ERROR&limit=20
```

### 向量存储性能问题

**症状**：向量检索延迟高。

**排查步骤**：

1. **检查索引类型**：
```bash
curl http://localhost:8000/api/v1/infra/vector-store/collections/knowledge_vectors/index-info
# 返回: {"index_type": "HNSW", "m": 16, "ef_construction": 256}
```

2. **检查向量数量**：
```bash
curl http://localhost:8000/api/v1/infra/vector-store/collections/knowledge_vectors/stats
# 返回: {"vector_count": 100000, "size_mb": 500}
```

3. **优化检索参数**：
```yaml
# 提高检索效率
vector_store:
  collections:
    - name: knowledge_vectors
      hnsw_config:
        m: 16  # 增加 M 可提高精度但降低写入速度
        ef_construction: 256
      search_params:
        ef: 64  # 增加 ef 可提高召回但降低检索速度
```

### Redis 连接超时

**排查步骤**：

1. **检查 Redis 服务状态**：
```bash
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping
```

2. **检查内存使用**：
```bash
redis-cli -h $REDIS_HOST INFO memory
```

3. **检查最大连接数**：
```bash
redis-cli -h $REDIS_HOST CONFIG GET maxclients
```

4. **优化连接池配置**：
```yaml
# 增加 max_connections
cache:
  pool:
    max_connections: 100
```

---

## 配置最佳实践

### 生产环境配置建议

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| DB 连接池 `max_size` | CPU 核心数 × 4 | 避免连接数过多 |
| DB 连接池 `recycle` | 3600 | 防止连接失效 |
| Redis `max_memory` | 系统内存 × 0.6 | 留有余量 |
| Redis `eviction_policy` | allkeys-lru | 自动清理 |
| LLM `retry.max_attempts` | 3 | 应对临时错误 |
| Vector Store `search_timeout` | 10 | 防止长时间等待 |

### 环境隔离

**开发环境**：`config/config.dev.yaml`
```yaml
environment: development

database:
  host: localhost
  pool:
    min_size: 2
    max_size: 10

logging:
  level: DEBUG
```

**生产环境**：`config/config.prod.yaml`
```yaml
environment: production

database:
  host: db.prod.internal
  pool:
    min_size: 10
    max_size: 50
    ssl:
      enabled: true

logging:
  level: WARNING
```

**切换环境**：
```bash
# 通过环境变量切换
export ENV=production
# 或
cp config/config.prod.yaml config/config.yaml
./scripts/restart-services.sh
```

---

## 相关链接

- [← 返回基础设施层文档](../index.md)
- [架构师指南](./architect/index.md) - 基础设施层架构设计
- [开发者指南](./developer/index.md) - 基础设施层开发指南
- [运维指南](./ops/index.md) - 基础设施层部署运维

---

*最后更新: 2026-04-10*

---

## 证据索引（Evidence Index｜抽样）

- 配置模型与默认值：`infra/*/schemas.py`（按模块）
- infra tests：`infra/tests/*`
