# AI Platform 测试指南

> 系统级测试策略、分层测试方法、跨层测试规范

---

## 📋 目录

- [测试策略](#测试策略)
- [分层测试原则](#分层测试原则)
- [测试类型](#测试类型)
- [测试环境](#测试环境)
- [跨层测试规范](#跨层测试规范)
- [测试覆盖率要求](#测试覆盖率要求)
- [CI/CD 集成](#cicd-集成)
- [各层测试指南](#各层测试指南)

---

## 测试策略

### 测试金字塔

AI Platform 采用测试金字塔策略，确保测试效率和可靠性：

```
        ┌─────────┐
        │   E2E   │  5-10%  端到端测试
        └─────────┘
      ┌─────────────┐
      │ Integration │  15-25%  集成测试
      └─────────────┘
    ┌───────────────────┐
    │    Unit Tests     │  70-80%  单元测试
    └───────────────────┘
```

**测试金字塔原则**：
- **单元测试**：数量最多，执行最快，测试独立单元
- **集成测试**：测试模块间的协作
- **E2E 测试**：验证完整用户场景

---

## 分层测试原则

### 各层测试职责

每个层级都有独立的测试职责，遵循单向依赖原则：

| 层级 | 测试职责 | 测试范围 |
|------|----------|----------|
| **Layer 0 (infra)** | 基础设施正确性 | 数据库连通性、LLM 连接、向量存储、消息队列 |
| **Layer 1 (core)** | 业务逻辑正确性 | Agent 执行、Skill 调用、编排流程、记忆系统 |
| **Layer 2 (platform)** | API 正确性 | REST/GraphQL 端点、认证授权、多租户隔离 |
| **Layer 3 (app)** | 用户体验正确性 | 消息网关、CLI 命令、Web UI 交互 |

### 测试依赖规则

**允许的测试依赖**：
```
infra 测试 → 无依赖（独立测试基础设施）
core 测试 → 可以使用 infra 的 Mock/Stub
platform 测试 → 可以使用 core 的 Mock/Stub
app 测试 → 可以使用 platform 的 Mock/Stub
```

**测试隔离原则**：
- 单元测试：完全隔离，使用 Mock/Stub
- 集成测试：测试真实集成点，使用测试容器
- E2E 测试：测试真实系统，使用专用测试环境

---

## 测试类型

### 1. 单元测试

**定义**：测试独立单元的逻辑正确性

**原则**：
- 测试单个函数/方法/类
- 使用 Mock/Stub 隔离外部依赖
- 快速执行（< 100ms per test）
- 覆盖边界条件、错误处理

**示例**：
```python
# infra 层单元测试
def test_database_client_build_query():
    client = DatabaseClient(config)
    query, params = client._build_query("SELECT * FROM users WHERE id = :id", {"id": 1})
    assert "SELECT" in query
    assert params == (1,)

# core 层单元测试
def test_agent_executor_with_mock_llm():
    mock_llm = MockLLM(responses=["test response"])
    executor = AgentExecutor(llm=mock_llm)
    result = executor.execute("test input")
    assert result.content == "test response"
```

**覆盖率要求**：
- 核心业务逻辑：≥ 90%
- 基础设施代码：≥ 80%
- API 端点：≥ 70%

---

### 2. 集成测试

**定义**：测试多个模块协作的正确性

**原则**：
- 测试真实集成点
- 使用测试容器（Testcontainers）管理外部服务
- 测试后清理资源
- 记录测试数据

**示例**：
```python
# infra 层集成测试
@pytest.fixture
async def postgres_container():
    container = PostgresContainer("postgres:15")
    container.start()
    yield container
    container.stop()

async def test_postgres_crud(postgres_container):
    client = PostgresClient(postgres_container.get_connection_url())
    await client.insert("users", {"name": "test"})
    users = await client.query("SELECT * FROM users")
    assert len(users) == 1

# core 层集成测试（使用真实数据库和 LLM Stub）
async def test_agent_with_real_database(test_db):
    agent = Agent(db=test_db, llm=StubLLM())
    result = await agent.execute("save user preference")
    assert result.success
```

**测试容器策略**：
- PostgreSQL/MySQL/MongoDB：使用官方测试容器
- Redis/RabbitMQ/Kafka：使用官方测试容器
- LLM API：使用 Mock 服务器
- 向量存储：使用 lightweight 容器（FAISS 内存模式）

---

### 3. 端到端测试

**定义**：验证完整的用户场景

**原则**：
- 测试真实用户场景
- 使用专用测试环境
- 测试后清理数据
- 避免过度依赖 E2E

**示例**：
```python
# E2E 测试 - 完整对话流程
async def test_user_chat_flow(test_app):
    # 1. 用户登录
    response = await test_app.post("/auth/login", json={"username": "test", "password": "test"})
    assert response.status_code == 200
    
    # 2. 创建 Agent
    response = await test_app.post("/agents", json={"name": "test-agent", "model": "gpt-4"})
    assert response.status_code == 201
    agent_id = response.json()["id"]
    
    # 3. 发送消息
    response = await test_app.post(f"/agents/{agent_id}/chat", json={"message": "hello"})
    assert response.status_code == 200
    
    # 4. 验证响应
    assert "content" in response.json()
```

---

### 4. 性能测试

**定义**：验证系统性能指标

**测试指标**：
| 指标 | 目标 | 工具 |
|------|------|------|
| 响应时间 | P95 < 500ms | locust、k6 |
| 吞吐量 | > 1000 QPS | locust、k6 |
| 并发数 | 支持 100 并发 | locust、k6 |
| LLM 调用延迟 | P95 < 3s | 自定义脚本 |

**示例**：
```python
# 性能测试 - API 吞吐量
def test_api_throughput(benchmark):
    result = benchmark(test_app.get, "/agents")
    assert result.stats.mean < 0.1  # 平均响应时间 < 100ms
```

---

### 5. 安全测试

**定义**：验证系统安全性

**测试内容**：
- 认证授权测试（JWT 验证、权限控制）
- SQL 注入测试
- XSS 攻击测试
- CSRF 保护测试
- API 密钥保护测试
- 敏感数据脱敏测试

**示例**：
```python
# 安全测试 - SQL 注入
async def test_sql_injection_prevention(test_app):
    response = await test_app.post("/agents", json={
        "name": "'; DROP TABLE agents; --",
        "model": "gpt-4"
    })
    assert response.status_code != 500
    assert "error" in response.json()
```

---

## 测试环境

### 环境分类

| 环境 | 用途 | 数据 | 隔离性 |
|------|------|------|--------|
| **单元测试** | 开发机本地 | Mock/Stub | 完全隔离 |
| **集成测试** | 开发机本地 | 测试容器 | 进程隔离 |
| **CI 测试** | CI Runner | 测试容器 | 容器隔离 |
| **测试环境** | 独立服务器 | 测试数据 | 环境隔离 |
| **预发环境** | 类生产配置 | 脱敏数据 | 环境隔离 |
| **生产环境** | 正式服务 | 生产数据 | 完全隔离 |

### 测试数据管理

**原则**：
- 单元测试：使用 Mock 数据，不依赖外部数据
- 集成测试：使用测试容器，测试后清理
- E2E 测试：使用专用测试数据库，测试后清理

**数据隔离策略**：
```python
# 每个测试使用独立数据库
@pytest.fixture
async def test_db():
    container = PostgresContainer("postgres:15")
    container.start()
    client = PostgresClient(container.get_connection_url())
    yield client
    container.stop()  # 测试后自动清理
```

---

## 跨层测试规范

### 测试边界

**规则**：
- infra 层测试：不依赖 core/platform/app
- core 层测试：可以使用 infra 的 Mock
- platform 层测试：可以使用 core 的 Mock
- app 层测试：可以使用 platform 的 Mock

**禁止**：
- core 测试使用真实数据库（应使用 Mock）
- platform 测试直接访问 infra（应通过 core Mock）
- app 测试直接访问 infra或 core（应通过 platform Mock）

### Mock 策略

**各层 Mock 规范**：

```python
# infra 层 Mock - 协议级别
class MockDatabaseClient:
    async def query(self, sql, params): ...
    async def insert(self, table, data): ...
    async def update(self, table, data, where): ...
    async def delete(self, table, where): ...

class MockLLMClient:
    async def chat(self, messages): ...
    async def embed(self, text): ...

# core 层 Mock - 业务级别
class MockAgentExecutor:
    async def execute(self, input): ...
    async def get_state(self): ...

class MockSkillExecutor:
    async def run(self, params): ...

# platform 层 Mock - API 级别
class MockAuthService:
    def verify_token(self, token): ...
    def create_token(self, user): ...

class MockTenantService:
    def get_tenant(self, tenant_id): ...
```

---

## 测试覆盖率要求

### 最低覆盖率

| 层级 | 单元测试 | 集成测试 | 总覆盖率 |
|------|----------|----------|----------|
| **infra** | ≥ 80% | ≥ 70% | ≥ 85% |
| **core** | ≥ 90% | ≥ 60% | ≥ 90% |
| **platform** | ≥ 70% | ≥ 70% | ≥ 85% |
| **app** | ≥ 60% | ≥ 60% | ≥ 70% |

### 覆盖率检查

```bash
# 检查覆盖率
pytest --cov=aiPlat_infra --cov-report=html
pytest --cov=aiPlat_core --cov-report=html
pytest --cov=aiPlat_platform --cov-report=html
pytest --cov=aiPlat_app --cov-report=html
```

---

## CI/CD 集成

### 测试阶段

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 单元测试     │ ──→ │ 集成测试     │ ──→ │ E2E 测试    │
│ (快速反馈)   │     │ (质量保证)   │     │ (场景验证)  │
└─────────────┘     └─────────────┘     └─────────────┘
```

### CI 配置示例

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit --cov --cov-report=xml
    
  integration-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v3
      - run: pytest tests/integration
  
  e2e-test:
    runs-on: ubuntu-latest
    needs: [unit-test, integration-test]
    steps:
      - run: pytest tests/e2e
```

### 测试门禁

**强制要求**：
- 单元测试：必须通过
- 集成测试：必须通过
- 覆盖率：≥ 85%（core 层）或 ≥ 70%（其他层）
- 安全扫描：必须通过

---

## 各层测试指南

### Layer 0: aiPlat-infra 测试指南

详见：[aiPlat-infra 测试指南](../aiPlat-infra/docs/testing/TESTING_GUIDE.md)

**测试重点**：
- 数据库连接测试（PostgreSQL、MySQL、MongoDB、SQLite）
- LLM 客户端测试（OpenAI、Anthropic、本地模型）
- 向量存储测试（FAISS、Milvus、ChromaDB）
- 消息队列测试（Kafka、RabbitMQ、Redis Streams）
- 缓存测试（Redis）
- 配置管理测试

**测试工具**：
- testcontainers（数据库、消息队列）
- pytest（测试框架）
- pytest-asyncio（异步测试）
- pytest-cov（覆盖率）

---

### Layer 1: aiPlat-core 测试指南

详见：[aiPlat-core 测试指南](../aiPlat-core/docs/testing/TESTING_GUIDE.md)

**架构概览**：
```
aiPlat-core/
├── adapters/          # 外部适配器
│   └── llm/          # LLM 适配器（OpenAI、Anthropic）
├── apps/             # 应用层
│   ├── agents/       # Agent 实现
│   ├── skills/       # Skill 实现
│   └── tools/        # Tool 实现
└── harness/          # 框架核心
    ├── interfaces/    # 接口定义
    ├── infrastructure/# 基础设施
    ├── execution/     # 执行系统
    ├── coordination/  # 协调系统
    ├── observability/ # 观察系统
    ├── feedback_loops/# 反馈循环
    ├── memory/        # 记忆系统
    ├── knowledge/     # 知识系统
    └── integration.py # 统一入口
```

**测试重点**：

#### 1. Harness 集成测试（P1 - 最高优先级）

```python
# tests/unit/test_harness/test_integration.py
class TestHarnessIntegration:
    """测试 HarnessIntegration 统一入口"""
    
    @pytest.mark.asyncio
    async def test_initialize_sets_up_components(self):
        """测试初始化设置所有启用的组件"""
        config = HarnessConfig(
            enable_observability=True,
            enable_memory=True,
            enable_feedback_loops=True,
        )
        harness = HarnessIntegration.initialize(config)
        
        assert harness._initialized is True
        assert harness._monitoring is not None
        assert harness._memory is not None
    
    @pytest.mark.asyncio
    async def test_create_agent_loop(self):
        """测试创建 Agent 循环"""
        harness = HarnessIntegration.initialize()
        mock_agent = MagicMock()
        
        loop = harness.create_agent_loop(mock_agent, loop_type="react")
        
        assert loop is not None
    
    @pytest.mark.asyncio
    async def test_full_flow(self, harness):
        """测试完整执行流程"""
        result = await harness.execute(
            agent_name="test_agent",
            input_data={"query": "test"}
        )
        
        assert result.status == "success"
        assert result.output is not None
```

#### 2. 记忆系统测试（P1）

```python
# tests/unit/test_harness/test_memory/test_base.py
class TestMemoryBase:
    """测试记忆系统基类"""
    
    @pytest.mark.asyncio
    async def test_memory_store_and_retrieve(self):
        """测试记忆存储和检索"""
        memory = ShortTermMemory(MemoryConfig(max_size=100))
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        # 存储
        entry_id = await memory.store(entry)
        assert entry_id == "test-1"
        
        # 检索
        results = await memory.retrieve("test")
        assert len(results) == 1
        assert results[0].id == "test-1"
    
    @pytest.mark.asyncio
    async def test_memory_with_embeddings(self):
        """测试带向量的记忆"""
        memory = LongTermMemory(MemoryConfig(persist=True))
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.SEMANTIC,
            embeddings=[0.1, 0.2, 0.3],  # 向量
        )
        
        await memory.store(entry)
        results = await memory.retrieve("test", use_embeddings=True)
        
        assert len(results) == 1
        assert results[0].embeddings is not None
```

#### 3. 执行系统测试（P1）

```python
# tests/unit/test_harness/test_execution/test_engine.py
class TestExecutionEngine:
    """测试执行引擎"""
    
    @pytest.mark.asyncio
    async def test_engine_execute_plan(self):
        """测试执行计划"""
        engine = ExecutionEngine(config)
        plan = ExecutionPlan(
            steps=[
                Step(id="s1", action="action1", params={"key": "value"}),
                Step(id="s2", action="action2", params={"key": "value"}),
            ]
        )
        
        result = await engine.execute(plan)
        
        assert result.status == "completed"
        assert len(result.step_results) == 2
    
    @pytest.mark.asyncio
    async def test_engine_with_error(self):
        """测试执行错误处理"""
        engine = ExecutionEngine(config)
        plan = ExecutionPlan(steps=[...])
        
        # Mock 一个失败步骤
        with patch.object(engine, '_run_step', side_effect=Exception("失败")):
            result = await engine.execute(plan)
            
            assert result.status == "failed"
            assert "失败" in result.error
```

#### 4. 协调系统测试（P2）

```python
# tests/unit/test_harness/test_coordination/test_patterns.py
class TestCoordinationPatterns:
    """测试协调模式"""
    
    @pytest.mark.asyncio
    async def test_sequential_pattern(self):
        """测试顺序执行模式"""
        pattern = SequentialPattern(config)
        
        pattern.add_step(mock_step1)
        pattern.add_step(mock_step2)
        
        result = await pattern.execute(input_data)
        
        assert result.steps_executed == ["step1", "step2"]
        assert result.status == "completed"
    
    @pytest.mark.asyncio
    async def test_parallel_pattern(self):
        """测试并行执行模式"""
        pattern = ParallelPattern(config)
        
        pattern.add_step(mock_step1)
        pattern.add_step(mock_step2)
        
        result = await pattern.execute(input_data)
        
        assert result.status == "completed"
        assert len(result.step_results) == 2
```

#### 5. LLM 适配器测试（P1）

```python
# tests/unit/test_adapters/test_llm/test_base.py
class TestOpenAIAdapter:
    """测试 OpenAI 适配器"""
    
    @pytest.mark.asyncio
    async def test_generate_with_mock(self):
        """测试生成功能（Mock）"""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(message=MagicMock(content="测试响应"))
            ]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            adapter = OpenAIAdapter(LLMConfig(model="gpt-4"))
            result = await adapter.generate("测试提示")
            
            assert result == "测试响应"
            mock_client.chat.completions.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_embed_with_mock(self):
        """测试向量嵌入功能（Mock）"""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            
            adapter = OpenAIAdapter(LLMConfig(model="text-embedding-3-small"))
            result = await adapter.embed("Test text")
            
            assert result == [0.1, 0.2, 0.3]
```

**测试优先级**：

| 模块 | 优先级 | 测试重点 | 覆盖率要求 |
|------|--------|----------|-----------|
| harness/integration | P1 | 统一入口、组件初始化 | ≥90% |
| harness/memory | P1 | 存储检索、过期清理 | ≥90% |
| harness/execution | P1 | 执行引擎、LangGraph 集成 | ≥90% |
| adapters/llm | P1 | 生成、嵌入、错误处理 | ≥90% |
| harness/coordination | P2 | 模式编排、收敛检测 | ≥85% |
| harness/knowledge | P2 | 知识检索、索引 | ≥85% |
| harness/observability | P3 | 监控、事件总线 | ≥80% |
| harness/feedback_loops | P3 | 反馈循环、演进引擎 | ≥80% |

**Mock 策略**：

```python
# core 层 Mock 规范

# 1. LLM Mock - 返回固定响应
class MockLLMAdapter:
    def __init__(self, responses=None):
        self.responses = responses or ["default response"]
        self.call_count = 0
    
    async def generate(self, prompt: str) -> str:
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return response
    
    async def embed(self, text: str) -> list:
        return [0.1] * 128  # 固定向量

# 2. Memory Mock - 内存存储
class MockMemoryStore:
    def __init__(self):
        self._store = {}
    
    async def store(self, key: str, value: Any) -> None:
        self._store[key] = value
    
    async def retrieve(self, key: str) -> Any:
        return self._store.get(key)

# 3. Agent Mock - 简单执行器
class MockAgent:
    def __init__(self, response: str = "mock response"):
        self.response = response
    
    async def execute(self, input_data: dict) -> dict:
        return {"status": "success", "output": self.response}
```

**集成测试策略**：

```python
# 使用真实组件的集成测试
@pytest.mark.integration
class TestHarnessIntegration:
    """Harness 集成测试"""
    
    @pytest.fixture
    async def harness_with_real_memory(self):
        """使用真实记忆系统的 Harness"""
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 100, "persist": False},
        )
        harness = HarnessIntegration.initialize(config)
        yield harness
        harness.reset()
    
    @pytest.mark.asyncio
    async def test_memory_persistence(self, harness_with_real_memory):
        """测试记忆持久化"""
        harness = harness_with_real_memory
        
        # 存储记忆
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        await harness.memory.store(entry)
        
        # 检索记忆
        results = await harness.memory.retrieve("test")
        
        assert len(results) == 1
        assert results[0].content == "Test content"
```

**测试覆盖率检查**：

```bash
# 检查 core 层覆盖率
cd aiPlat-core
PYTHONPATH=./core python -m pytest core/tests/unit --cov=harness --cov=adapters --cov-report=html

# 检查各模块覆盖率
pytest core/tests/unit/test_harness/test_memory --cov=harness.memory --cov-report=term-missing
pytest core/tests/unit/test_harness/test_execution --cov=harness.execution --cov-report=term-missing
pytest core/tests/unit/test_adapters --cov=adapters --cov-report=term-missing
```

**测试工具**：

| 工具 | 用途 | 优先级 |
|------|------|--------|
| pytest | 测试框架 | 必需 |
| pytest-asyncio | 异步测试支持 | 必需 |
| pytest-cov | 覆盖率报告 | 必需 |
| unittest.mock | Mock 库 | 必需 |
| pytest-mock | pytest Mock 集成 | 推荐 |

---

### Layer 2: aiPlat-platform 测试指南

> 待补充

**测试重点**：
- REST API 测试
- GraphQL API 测试
- 认证授权测试
- 多租户隔离测试
- API 网关测试

---

### Layer 3: aiPlat-app 测试指南

> 待补充

**测试重点**：
- 消息网关测试
- CLI 命令测试
- Web UI 组件测试

---

## 测试最佳实践

### 1. 测试命名规范

```python
# 格式：test_<功能>_<场景>_<预期结果>
def test_agent_execute_with_valid_input_returns_result():
    ...

def test_agent_execute_with_invalid_input_raises_error():
    ...

def test_database_insert_with_duplicate_key_fails():
    ...
```

### 2. 测试组织结构

```
tests/
├── unit/              # 单元测试
│   ├── infra/
│   ├── core/
│   ├── platform/
│   └── app/
├── integration/        # 集成测试
│   ├── infra/
│   ├── core/
│   ├── platform/
│   └── app/
├── e2e/               # 端到端测试
│   └── scenarios/
└── performance/       # 性能测试
    ├── locustfile.py
    └── k6_script.js
```

### 3. 测试夹具（Fixtures）

```python
# conftest.py - 共享测试夹具
@pytest.fixture
async def test_db():
    """提供测试数据库"""
    container = PostgresContainer("postgres:15")
    container.start()
    client = PostgresClient(container.get_connection_url())
    yield client
    container.stop()

@pytest.fixture
def mock_llm():
    """提供 Mock LLM"""
    return MockLLM(responses=["test response"])

@pytest.fixture
def test_app(test_db, mock_llm):
    """提供测试应用"""
    app = create_app(db=test_db, llm=mock_llm)
    yield app
```

### 4. 测试数据管理

```python
# 使用 Factory Boy 创建测试数据
class UserFactory(factory.Factory):
    class Meta:
        model = User
    
    id = factory.Sequence(lambda n: n)
    name = factory.Faker('name')
    email = factory.Faker('email')

# 使用 Faker 生成随机数据
from faker import Faker
fake = Faker()

def test_create_user():
    user = UserFactory(name=fake.name(), email=fake.email())
    ...
```

---

## 测试工具清单

### 测试框架

| 工具 | 用途 | 优先级 |
|------|------|--------|
| pytest | 测试框架 | 必需 |
| pytest-asyncio | 异步测试支持 | 必需 |
| pytest-cov | 覆盖率报告 | 必需 |
| pytest-benchmark | 性能基准测试 | 推荐 |
| pytest-xdist | 并行测试 | 推荐 |

### Mock 工具

| 工具 | 用途 | 优先级 |
|------|------|--------|
| unittest.mock | Mock 库 | 必需 |
| pytest-mock | pytest 集成 | 推荐 |
| httpx-mock | HTTP Mock | 推荐 |

### 测试容器

| 工具 | 用途 | 优先级 |
|------|------|--------|
| testcontainers | 数据库容器 | 必需 |
| docker | 容器运行时 | 必需 |

### API 测试

| 工具 | 用途 | 优先级 |
|------|------|--------|
| httpx | HTTP 客户端 | 必需 |
| FastAPI TestClient | API 测试 | 必需 |

### 性能测试

| 工具 | 用途 | 优先级 |
|------|------|--------|
| locust | 负载测试 | 推荐 |
| k6 | 性能测试 | 推荐 |

---

## 故障排查

### 常见问题

**1. 测试容器启动慢**
- 原因：Docker 镜像大，首次下载慢
- 解决：预下载镜像，使用本地镜像缓存

**2. 测试相互影响**
- 原因：测试数据未清理
- 解决：每个测试后清理数据，使用独立数据库

**3. 异步测试超时**
- 原因：异步操作未正确等待
- 解决：使用 `pytest-asyncio`，正确 await

**4. Mock 未生效**
- 原因：Mock 位置错误
- 解决：Mock 具体实现而非接口

---

## 测试文档结构

```
aiPlatform/
└── docs/
    └── TESTING_GUIDE.md          # 系统级测试指南（本文档）
    
aiPlat-infra/
└── docs/testing/
    ├── TESTING_GUIDE.md          # infra 层测试指南
    ├── TESTING_QUICKSTART.md     # 快速开始
    ├── SYSTEM_TESTING_GUIDE.md   # 详细测试指南
    └── reports/                  # 测试报告

aiPlat-core/
└── docs/testing/
    └── TESTING_GUIDE.md          # core 层测试指南（待补充）

aiPlat-platform/
└── docs/testing/
    └── TESTING_GUIDE.md          # platform 层测试指南（待补充）

aiPlat-app/
└── docs/testing/
    └── TESTING_GUIDE.md          # app 层测试指南（待补充）
```

---

## 📌 文档版本与代码版本对应

| 文档版本 | 对应代码版本 | 说明 |
|----------|-------------|------|
| 1.0.0 | v1.0.0 | 初始版本 |
| 最新 | main | 开发中 |

---

*最后更新: 2026-04-11*