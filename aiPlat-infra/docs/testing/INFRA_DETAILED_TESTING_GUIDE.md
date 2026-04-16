# AI Platform 基础设施层 - 完整测试体系指南（设计真值：以代码事实为准）

> 说明：本文档描述 infra 的系统级测试策略。若涉及外部 CI/CD、部署工件或平台层策略，请视为 To-Be 或外部仓库内容；As-Is 以 `infra/tests/*` 与 `docs/testing/reports/*` 的可复现报告为准。

> 系统级测试策略、模块测试指南、集成测试规范

---

## 📋 目录

- [系统架构概览](#系统架构概览)
- [测试策略](#测试策略)
- [模块测试指南](#模块测试指南)
- [集成测试指南](#集成测试指南)
- [系统级测试](#系统级测试)
- [性能测试](#性能测试)
- [安全测试](#安全测试)
- [CI/CD集成](#cicd集成)
- [故障排查](#故障排查)

---

## 系统架构概览

### 模块架构图

```
AI Platform 基础设施层
│
├── 核心层 (Core)
│   ├── config          # 配置管理
│   ├── di              # 依赖注入
│   ├── utils           # 工具函数
│   └── logging         # 日志系统
│
├── 数据层 (Data)
│   ├── database        # 数据库访问
│   │   ├── SQLite      # 本地数据库
│   │   ├── PostgreSQL  # 关系型数据库
│   │   ├── MySQL       # 关系型数据库
│   │   └── MongoDB     # 文档数据库
│   │
│   ├── vector          # 向量存储
│   │   ├── Faiss       # 本地向量库
│   │   ├── Milvus      # 分布式向量库
│   │   ├── ChromaDB    # 向量数据库
│   │   └── Pinecone    # 云向量服务
│   │
│   └── storage         # 对象存储
│       ├── Local       # 本地存储
│       ├── S3          # AWS S3
│       └── MinIO       # 自建对象存储
│
├── 通信层 (Communication)
│   ├── messaging       # 消息队列
│   │   ├── Kafka       # 流式消息
│   │   ├── RabbitMQ    # 消息队列
│   │   └── Redis       # 消息流
│   │
│   ├── http            # HTTP客户端
│   └── network         # 网络管理
│
├── 计算层 (Compute)
│   ├── llm             # 大语言模型
│   │   ├── OpenAI      # GPT系列
│   │   ├── Anthropic   # Claude系列
│   │   └── Local       # 本地模型
│   │
│   ├── mcp             # 模型控制协议
│   └── memory          # 内存管理
│       ├── CPU         # CPU内存
│       └── GPU         # GPU内存
│
└── 监控层 (Observability)
    ├── monitoring      # 指标监控
    ├── tracing         # 分布式追踪
    └── cache           # 缓存管理
```

### 数据流图

```
入站请求
    │
    ▼
[HTTP客户端] ──→ [配置管理] ──→ [依赖注入]
    │                                │
    ▼                                ▼
[消息队列]                       [数据库]
    │                                │
    │                                ▼
    │                          [向量存储]
    │                                │
    └────────────┬───────────────────┘
                 │
                 ▼
            [LLM处理]
                 │
                 ▼
            [缓存层]
                 │
                 ▼
            [监控追踪]
                 │
                 ▼
             出站响应
```

---

## 测试策略

### 三层测试金字塔

```
        ┌─────────────┐
        │   E2E测试   │  10% - 端到端集成测试
        └─────────────┘
       ┌───────────────┐
       │  集成测试      │  20% - 模块间交互测试
       └───────────────┘
      ┌─────────────────┐
      │    单元测试     │  70% - 函数级测试
      └─────────────────┘
```

### 测试类型分布

| 测试类型 | 占比 | 执行时间 | Docker需求 | 用途 |
|---------|------|---------|-----------|------|
| **单元测试** | 70% | ~1秒 | 不需要 | 快速验证函数逻辑 |
| **集成测试** | 20% | ~10秒 | 需要 | 验证模块交互 |
| **E2E测试** | 10% | ~1分钟 | 需要 | 验证完整流程 |

### 测试策略矩阵

| 模块类型 | 单元测试 | 集成测试 | E2E测试 | Mock测试 |
|---------|---------|---------|---------|---------|
| **Core核心** | ✅ 必须 | ❌ 不需要 | ❌ 不需要 | ⚠️ 可选 |
| **Database** | ✅ 必须 | ✅ 必须 | ⚠️ 可选 | ⚠️ 可选 |
| **Vector** | ✅ 必须 | ✅ 推荐 | ❌ 不需要 | ✅ 必须 |
| **Messaging** | ✅ 必须 | ✅ 必须 | ⚠️ 可选 | ✅ 必须 |
| **LLM** | ✅ 必须 | ⚠️ 可选 | ❌ 不需要 | ✅ 必须 |
| **Storage** | ✅ 必须 | ✅ 推荐 | ❌ 不需要 | ⚠️ 可选 |

---

## 模块测试指南

### 1. 核心模块测试 (Core)

#### Config模块

**测试内容:**
- 配置加载（YAML/JSON/环境变量）
- 配置验证和类型转换
- 配置合并和覆盖
- 默认值处理

**测试模板:**
```python
# infra/tests/test_config/test_config.py

def test_config_loading_from_yaml():
    """测试从YAML文件加载配置"""
    config = Config.from_yaml("config/default.yaml")
    assert config.database.host == "localhost"
    assert config.database.port == 5432

def test_config_validation():
    """测试配置验证"""
    with pytest.raises(ValidationError):
        Config(database={"port": "invalid"})

def test_config_merge():
    """测试配置合并"""
    base = Config.from_yaml("config/default.yaml")
    override = Config.from_yaml("config/production.yaml")
    merged = Config.merge(base, override)
    assert merged.database.pool.max_size == 50
```

**覆盖率目标:** 90%+

#### DI模块

**测试内容:**
- 容器注册和解析
- 单例管理
- 依赖注入
- 生命周期管理

**测试模板:**
```python
# infra/tests/test_di/test_container.py

def test_container_register_and_resolve():
    """测试容器注册和解析"""
    container = Container()
    container.register(DatabaseClient, PostgresClient)
    
    client = container.resolve(DatabaseClient)
    assert isinstance(client, PostgresClient)

def test_singleton_lifecycle():
    """测试单例生命周期"""
    container = Container()
    container.register(DatabaseClient, PostgresClient, lifecycle="singleton")
    
    client1 = container.resolve(DatabaseClient)
    client2 = container.resolve(DatabaseClient)
    assert client1 is client2
```

**覆盖率目标:** 85%+

#### Utils模块

**测试内容:**
- 验证器（email, URL, phone等）
- 辅助函数（时间、JSON、加密等）
- 错误处理

**覆盖率目标:** 80%+

---

### 2. 数据库模块测试 (Database)

#### SQLite模块

**测试内容:**
- CRUD操作
- 事务管理
- 连接池
- 错误处理

**测试模板:**
```python
# infra/tests/test_database/test_client.py

@pytest.mark.asyncio
async def test_sqlite_crud_operations():
    """测试SQLite CRUD操作"""
    config = DatabaseConfig(type="sqlite", name=":memory:")
    client = SqliteClient(config)
    await client.connect()
    
    # CREATE
    await client.execute("CREATE TABLE users (id INT, name TEXT)")
    
    # INSERT
    await client.execute("INSERT INTO users VALUES (?, ?)", (1, "Alice"))
    
    # SELECT
    results = await client.execute("SELECT * FROM users WHERE id = ?", (1,))
    assert len(results) == 1
    assert results[0]["name"] == "Alice"
    
    # UPDATE
    await client.execute("UPDATE users SET name = ? WHERE id = ?", ("Bob", 1))
    
    # DELETE
    await client.execute("DELETE FROM users WHERE id = ?", (1,))
    
    await client.close()
```

**集成测试（真实数据库）:**
```python
# infra/tests/test_database/test_integration.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_real_operations(postgres_container):
    """测试PostgreSQL真实数据库操作"""
    # 使用Testcontainers启动真实PostgreSQL
    client = PostgresClient(config_from_container(postgres_container))
    await client.connect()
    
    # 测试真实SQL操作
    await client.execute("CREATE TABLE users (id SERIAL, name VARCHAR)")
    await client.execute("INSERT INTO users (name) VALUES ($1)", ("Alice",))
    
    results = await client.execute("SELECT * FROM users")
    assert len(results) == 1
    assert results[0]["name"] == "Alice"
    
    await client.close()
```

**覆盖率目标:** 85%+

#### PostgreSQL/MySQL/MongoDB模块

**单元测试:** 配置验证、客户端创建  
**集成测试:** 真实数据库CRUD、事务、连接池

**覆盖率目标:** 80%+

---

### 3. 向量存储模块测试 (Vector)

#### Faiss模块

**测试内容:**
- 向量添加/删除/搜索
- 索引创建和加载
- 相似度计算
- 批量操作

**测试模板:**
```python
# infra/tests/test_vector/test_client.py

@pytest.mark.asyncio
async def test_faiss_add_and_search():
    """测试Faiss添加和搜索"""
    config = VectorConfig(type="faiss", dimension=128)
    store = FaissStore(config)
    
    # 添加向量
    ids = await store.add([
        Vector(id="1", values=[0.1] * 128),
        Vector(id="2", values=[0.2] * 128),
    ])
    assert len(ids) == 2
    
    # 搜索相似向量
    results = await store.search(query_vector=[0.1] * 128, top_k=2)
    assert len(results) == 2
    assert results[0].id == "1"
    assert results[0].score > 0.9
```

**Mock测试:**
```python
# 对于需要外部服务的Milvus/ChromaDB/Pinecone

@pytest.mark.asyncio
async def test_milvus_with_mock():
    """使用Mock测试Milvus"""
    with patch('infra.vector.milvus.MilvusClient') as mock_client:
        mock_client.insert.return_value = MagicMock(insert_result=[MagicMock(insert_count=2)])
        
        store = MilvusStore(config)
        await store.add([Vector(id="1", values=[0.1] * 128)])
        
        mock_client.insert.assert_called_once()
```

**覆盖率目标:** 85%+

---

### 4. 消息队列模块测试 (Messaging)

#### Redis Streams模块

**单元测试:** 配置验证、客户端创建  
**集成测试:** 真实Redis Streams发布/订阅/确认

**测试模板:**
```python
# infra/tests/test_messaging/test_redis_streams_integration.py

@pytest.mark.asyncio
async def test_redis_streams_operations(redis_container):
    """测试Redis Streams真实操作"""
    client = RedisClient(config_from_container(redis_container))
    
    # 发布消息
    await client.publish(
        topic="orders",
        message=json.dumps({"order_id": "123"}).encode()
    )
    
    # 订阅和消费
    received = []
    async def handler(msg):
        received.append(msg)
    
    await client.subscribe(topic="orders", handler=handler)
    await asyncio.sleep(1)
    
    assert len(received) > 0
    assert received[0].body == json.dumps({"order_id": "123"}).encode()
```

**覆盖率目标:** 80%+

---

### 5. LLM模块测试 (LLM)

#### OpenAI/Anthropic模块

**测试内容:**
- API调用（需要Mock）
- 响应解析
- 流式处理
- 错误处理

**Mock测试:**
```python
# infra/tests/test_llm/test_client.py

@pytest.mark.asyncio
async def test_openai_complete_with_mock():
    """使用Mock测试OpenAI完成"""
    with patch('openai.ChatCompletion.create') as mock_create:
        mock_create.return_value = {
            "choices": [{"message": {"content": "Hello, world!"}}]
        }
        
        client = OpenAIClient(config)
        result = await client.complete("Say hello")
        
        assert result == "Hello, world!"
        mock_create.assert_called_once_with(model="gpt-4", messages=[...])
```

**覆盖率目标:** 75%+

#### Local LLM模块

**集成测试:** 需要本地模型文件

**覆盖率目标:** 60%+

---

### 6. 存储模块测试 (Storage)

#### Local/S3/MinIO模块

**单元测试:** 配置验证、客户端创建  
**集成测试:** 真实上传/下载/删除

**测试模板:**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_s3_operations(minio_container):
    """测试MinIO对象存储操作"""
    client = S3Client(config_from_container(minio_container))
    
    # 上传
    await client.upload("bucket", "file.txt", b"content")
    
    # 下载
    content = await client.download("bucket", "file.txt")
    assert content == b"content"
    
    # 删除
    await client.delete("bucket", "file.txt")
```

**覆盖率目标:** 80%+

---

### 7. 计算模块测试 (Compute)

#### Memory模块

**测试内容:**
- GPU内存监控
- 模型加载/卸载
- 内存优化

**覆盖率目标:** 70%+

#### MCP模块

**测试内容:**
- 协议实现
- WebSocket通信
- 错误处理

**覆盖率目标:** 70%+

---

### 8. 监控层测试 (Observability)

#### Monitoring/Tracing/Cache

**测试内容:**
- 指标收集
- 分布式追踪
- 缓存策略

**覆盖率目标:** 75%+

---

## 集成测试指南

### Testcontainers使用规范

#### 1. 容器配置

**标准配置:**
```python
# conftest.py

@pytest.fixture(scope="session")
def postgres_container():
    """PostgreSQL容器fixture"""
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    yield container.get_connection_url()
    container.stop()

@pytest.fixture(scope="session")
def redis_container():
    """Redis容器fixture"""
    container = RedisContainer("redis:7-alpine")
    container.start()
    yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}"
    container.stop()

@pytest.fixture(scope="session")
def mongodb_container():
    """MongoDB容器fixture"""
    container = MongoDbContainer("mongo:7.0")
    container.start()
    host = container.get_container_host_ip()
    port = container.get_exposed_port(27017)
    yield f"mongodb://{host}:{port}"
    container.stop()
```

#### 2. 测试隔离

**原则:**
- 每个测试使用独立数据库/队列
- 测试结束后清理数据
- 容器session级别共享，数据库function级别隔离

**示例:**
```python
@pytest.mark.asyncio
async def test_user_operations(postgres_container):
    """测试用户操作 - 使用独立数据库"""
    # 创建测试专用数据库
    config = create_test_config(postgres_container, db_name=f"test_{uuid.uuid4().hex[:8]}")
    client = PostgresClient(config)
    
    try:
        await client.connect()
        # 测试操作...
    finally:
        # 清理测试数据
        await client.execute("DROP DATABASE IF EXISTS test_db")
        await client.close()
```

#### 3. 资源管理

**最佳实践:**
```python
# ✅ 好的实践：使用try-finally确保清理
async def test_with_cleanup():
    client = create_client()
    try:
        await client.connect()
        # 测试操作
    finally:
        await client.close()  # 总是清理

# ❌ 坏的实践：可能忘记清理
async def test_without_cleanup():
    client = create_client()
    await client.connect()
    # 测试操作
    # 可能忘记close()
```

---

## 系统级测试

### E2E测试场景

#### 场景1: 完整数据处理流程

```python
# tests/e2e/test_data_pipeline.py

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_data_pipeline():
    """测试完整数据处理流程"""
    # 1. 接收HTTP请求
    request_data = {"query": "What is AI?"}
    
    # 2. 存入数据库
    await database.insert("requests", request_data)
    
    # 3. 发送到消息队列
    await messaging.publish("requests", json.dumps(request_data).encode())
    
    # 4. 消费消息并处理
    message = await messaging.consume("requests")
    
    # 5. 调用LLM处理
    response = await llm.complete(message.body.decode())
    
    # 6. 存储到向量库
    embedding = await llm.embed(response)
    await vector_store.add([Vector(id=str(uuid.uuid4()), values=embedding)])
    
    # 7. 缓存结果
    await cache.set("response:" + request_id, response)
    
    # 8. 返回结果
    assert response is not None
    assert len(embedding) == 1536
```

#### 场景2: 微服务通信流程

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_microservice_communication():
    """测试微服务间通信"""
    # 服务A发送消息到服务B
    await service_a.publish("order.created", order_data)
    
    # 服务B接收并处理
    await service_b.subscribe("order.created", handler)
    
    # 验证消息传递
    assert handler.called
    assert handler.called_with(order_data)
```

---

## 性能测试

### 性能指标

| 指标 | 目标值 | 测试方法 |
|------|--------|---------|
| **数据库查询响应** | < 100ms | 插入1000条，查询时间 |
| **向量搜索延迟** | < 50ms | 搜索10000向量 |
| **消息吞吐量** | > 10000 msg/s | 压测工具 |
| **并发连接** | > 1000 | 并发测试 |

### 性能测试模板

```python
# tests/performance/test_database_performance.py

@pytest.mark.performance
@pytest.mark.asyncio
async def test_database_bulk_insert():
    """测试数据库批量插入性能"""
    client = PostgresClient(config)
    await client.connect()
    
    # 插入1000条记录
    start_time = time.time()
    
    tasks = [
        client.execute("INSERT INTO users (name) VALUES ($1)", (f"user_{i}",))
        for i in range(1000)
    ]
    await asyncio.gather(*tasks)
    
    elapsed_time = time.time() - start_time
    
    # 验证性能
    assert elapsed_time < 5.0  # 应在5秒内完成
    print(f"Insert 1000 records in {elapsed_time:.2f}s")
    
    await client.close()
```

---

## 安全测试

### 安全检查清单

- [ ] SQL注入测试
- [ ] XSS攻击测试
- [ ] 认证授权测试
- [ ] 敏感数据加密
- [ ] API密钥管理
- [ ] 权限边界测试

### 安全测试示例

```python
@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection():
    """测试SQL注入防护"""
    client = PostgresClient(config)
    await client.connect()
    
    # 尝试SQL注入
    malicious_input = "'; DROP TABLE users; --"
    
    # 应该被参数化查询防护
    with pytest.raises(Exception):
        await client.execute(
            f"SELECT * FROM users WHERE name = '{malicious_input}'"
        )
    
    # 使用参数化查询应该是安全的
    result = await client.execute(
        "SELECT * FROM users WHERE name = $1",
        (malicious_input,)
    )
    assert len(result) == 0  # 无结果，注入失败
```

---

## CI/CD集成

### GitHub Actions配置

```yaml
# .github/workflows/test.yml

name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -e .[dev]
      - name: Run unit tests
        run: |
          pytest infra/tests/ -v -m "not integration" --cov=infra --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_PASSWORD: test
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: test
      mongodb:
        image: mongo:7.0
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Run integration tests
        run: |
          pytest infra/tests/test_database/test_integration.py -v -m integration
          pytest infra/tests/test_messaging/ -v -m integration

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E tests
        run: |
          pytest tests/e2e/ -v --tb=short
```

---

## 故障排查

### 常见问题

#### 1. 测试失败：连接超时

**症状:**
```
ConnectionError: Cannot connect to localhost:5432
```

**解决方案:**
```python
# 检查Docker容器状态
docker ps

# 重启容器
docker restart postgres_container

# 增加超时时间
pytest --timeout=60
```

#### 2. 测试失败：数据库锁定

**症状:**
```
DatabaseLockedError: database is locked
```

**解决方案:**
```python
# SQLite使用内存数据库
config = DatabaseConfig(type="sqlite", name=":memory:")

# 或清理测试数据
await client.execute("DELETE FROM test_table")
```

#### 3. 测试失败：端口冲突

**症状:**
```
OSError: [Errno 48] Address already in use
```

**解决方案:**
```python
# 使用Testcontainers自动端口分配
container = PostgresContainer("postgres:15-alpine")
# 不需要指定端口，Testcontainers会自动分配

# 或手动管理端口
import socket
def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]
```

#### 4. 测试失败：资源泄漏

**症状:**
```
ResourceWarning: unclosed <socket.socket fd=123>
```

**解决方案:**
```python
# 使用async context manager
async with client as c:
    await c.execute(...)

# 或确保finally块清理
try:
    client = create_client()
    await client.connect()
finally:
    await client.close()
```

---

## 测试命令速查表

### 单元测试
```bash
# 运行所有单元测试
pytest infra/tests/ -v

# 运行特定模块
pytest infra/tests/test_database/ -v

# 运行单个测试文件
pytest infra/tests/test_database/test_client.py -v

# 运行单个测试函数
pytest infra/tests/test_database/test_client.py::TestDatabase::test_postgres -v

# 只运行单元测试（跳过集成测试）
pytest infra/tests/ -v -m "not integration"
```

### 集成测试
```bash
# 运行数据库集成测试
python infra/tests/test_database/run_all_integration_tests.py

# 运行Messaging集成测试
python infra/tests/test_messaging/run_all_messaging_tests.py

# 运行单个数据库测试
pytest infra/tests/test_database/test_postgres_integration.py -v -m integration
```

### 测试覆盖率
```bash
# 生成覆盖率报告
pytest infra/tests/ --cov=infra --cov-report=html

# 只测试特定模块的覆盖率
pytest infra/tests/test_database/ --cov=infra.database --cov-report=term

# 生成XML覆盖率报告（用于CI）
pytest infra/tests/ --cov=infra --cov-report=xml
```

### 性能测试
```bash
# 运行性能测试
pytest tests/performance/ -v -m performance

# 运行压力测试
pytest tests/performance/ -v --count=100
```

### 安全测试
```bash
# 运行安全测试
pytest tests/security/ -v -m security

# 运行所有安全相关测试
pytest -v -m security
```

---

## 测试报告模板

### 每日测试报告

```markdown
# 测试日报 - YYYY-MM-DD

## 测试执行情况

### 单元测试
- 总数: XX
- 通过: XX
- 失败: XX
- 覆盖率: XX%

### 集成测试
- 总数: XX
- 通过: XX
- 失败: XX
- 跳过: XX

## 失败用例分析

### 用例1: test_postgres_connection
- **错误信息**: Connection timeout
- **原因**: Docker容器启动慢
- **解决方案**: 增加超时时间

## 改进建议

1. 增加集成测试超时时间
2. 添加更多边界测试用例
3. 改进测试数据清理流程

## 下一步计划

- [ ] 修复失败用例
- [ ] 增加性能测试
- [ ] 优化测试执行时间
```

---

## 联系方式和资源

### 文档资源

- **测试最佳实践**: `docs/TESTING_GUIDE.md`
- **测试检查清单**: `docs/TESTING_CHECKLIST.md`
- **集成测试报告**: `INTEGRATION_TEST_REPORT.md`
- **系统测试总结**: `INTEGRATION_TESTS_SUMMARY.md`

### 外部资源

- [Testcontainers文档](https://testcontainers.com/)
- [pytest文档](https://docs.pytest.org/)
- [pytest-asyncio文档](https://pytest-asyncio.readthedocs.io/)

---

*最后更新: 2026-04-11  

---

## 证据索引（Evidence Index｜抽样）

- 测试入口：`infra/tests/*`
- 测试报告：`docs/testing/reports/*`
**文档版本**: v1.0  
**维护者**: AI Platform Team

---

**记住：好的测试不仅验证代码正确性，还作为文档和示例！**
