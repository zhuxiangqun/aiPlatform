# AI Platform基础设施层 - 测试指南（设计真值：以代码事实为准）

> 说明：本文档描述 infra 测试策略与常见错误。若引用外部 CI/部署工件，请视为 To-Be 或外部仓库内容；As-Is 以 `infra/tests/*` 可运行性为准。

> 避免空实现通过测试的最佳实践

---

## 📋 目录

- [问题背景](#问题背景)
- [测试原则](#测试原则)
- [测试分类](#测试分类)
- [最佳实践](#最佳实践)
- [常见错误](#常见错误)
- [测试模板](#测试模板)
- [检查清单](#检查清单)
- [示例参考](#示例参考)

---

## 问题背景

### 空实现通过了测试的原因

在经验审查中发现，所有模块的测试覆盖率极低（0%-30%），但都能通过测试。根本原因：

#### 1️⃣ **只测试对象创建，不调用方法**

```python
# ❌ 错误示例：测试只创建对象
def test_vector_store(self):
    store = FaissStore(config)
    assert store is not None  # 这证明不了任何功能！
```

**问题**：这样的测试即使实现全是空的也能通过！

```python
# 空实现也能通过测试
class FaissStore:
    def __init__(self, config):
        pass  # 什么都不做，但 assert store is not None 通过了！
```

#### 2️⃣ **验证属性存在而非功能可用**

```python
# ❌ 错误示例：只验证方法存在
def test_create_client(self):
    client = create_messaging_client(config)
    assert hasattr(client, "publish")      # 只证明方法存在
    assert hasattr(client, "subscribe")    # 不证明方法能工作！
```

**问题**：`hasattr()` 无法验证方法功能！

```python
# 空方法也能通过 hasattr 检查
class KafkaClient:
    def publish(self, topic, message):
        pass  # 空方法，但 hasattr 返回 True！
```

#### 3️⃣ **集成测试全部跳过**

```python
# ❌ 错误示例：跳过集成测试
@pytest.mark.integration
class TestMessagingIntegration:
    async def test_kafka_publish_subscribe(self):
        pytest.skip("Requires running Kafka instance")
        # 应该用 mock 代替直接跳过！
```

**问题**：核心功能完全没有被测试！

#### 4️⃣ **没有返回值验证**

```python
# ❌ 错误示例：不验证返回值内容
def test_list_nodes(self):
    nodes = manager.list_nodes()
    assert len(nodes) > 0  # 只验证数量，不验证内容！
```

**问题**：返回空字典列表也能通过！

```python
def list_nodes(self):
    return [{}]  # 空字典列表，len > 0 但内容错误！
```

---

## 测试原则

### 🎯 核心原则：**测试功能，而不是测试结构**

#### ✅ 好的测试 - 调用方法并验证返回值

```python
async def test_faiss_add_vectors(self):
    """测试添加向量"""
    store = FaissStore(config)
    
    # 1. 创建测试数据
    vectors = [
        Vector(id="v1", values=[1.0] * 128, metadata={"type": "test"}),
        Vector(id="v2", values=[2.0] * 128, metadata={"type": "test"}),
    ]
    
    # 2. 真实调用方法
    ids = await store.add(vectors)
    
    # 3. 验证返回值
    assert len(ids) == 2
    assert ids[0] == "v1"
    assert ids[1] == "v2"
```

#### ✅ 测试覆盖率统计

| 模块 | 之前 | 现在 | 提升 | 关键改进 |
|------|------|------|------|---------|
| **vector** | ~5% | **92%** | +87% | 真实功能测试 |
| **database** | ~0% | 待补充 | - | MongoDB查询 |
| **messaging** | ~15% | 待补充 | - | ack/nack验证 |
| **llm** | ~2% | 待补充 | - | chat/embed测试 |

---

## 测试分类

### 单元测试（Unit Tests）

**定义**：测试单个方法或函数的功能

```python
class TestVectorStore:
    @pytest.mark.asyncio
    async def test_faiss_add_vectors(self):
        """单元测试：测试添加向量功能"""
        store = FaissStore(VectorConfig(dimension=128))
        
        vectors = [Vector(id="test", values=[1.0] * 128)]
        ids = await store.add(vectors)  # 调用方法
        
        assert len(ids) == 1  # 验证返回值
        assert ids[0] == "test"  # 验证内容
```

**标记**：无特殊标记，默认为单元测试

### 集成测试（Integration Tests）

**定义**：测试多个组件协作或需要外部服务

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"),
                    reason="需要真实Kafka服务")
class TestKafkaIntegration:
    async def test_kafka_real_connection(self):
        """集成测试：测试真实Kafka连接"""
        client = create_messaging_client(config)
        await client.publish("test.topic", b"test message")
        # 使用真实服务...
```

**标记**：`@pytest.mark.integration`

### Mock测试（Mock Tests）

**定义**：使用Mock模拟外部依赖

```python
from unittest.mock import Mock, AsyncMock, patch

class TestMilvusStore:
    @pytest.mark.asyncio
    async def test_milvus_add_vectors(self):
        """Mock测试：不需要真实Milvus服务"""
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            # 设置Mock行为
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # 创建store并注入mock
            store = MilvusStore(config)
            store._client = mock_client
            store._initialized = True
            
            # 测试方法调用
            vectors = [Vector(id="v1", values=[1.0] * 128)]
            ids = await store.add(vectors)
            
            # 验证返回值
            assert len(ids) == 1
```

**标记**：无特殊标记，单元测试的一种

---

## 最佳实践

### 🎯 实践1：真实调用方法 + 验证返回值

```python
# ✅ 好的测试
async def test_database_insert(self):
    client = MongoClient(config)
    await client.connect()
    
    # 真实调用
    result = await client.execute(
        "insert into users (name) values (:name)",
        {"name": "test"}
    )
    
    # 验证返回值
    assert result is not None
    assert "inserted_id" in result
    assert result["affected_rows"] == 1
    
    # 验证数据确实存在
    rows = await client.execute("select * from users where name = :name", {"name": "test"})
    assert len(rows) == 1
    assert rows[0]["name"] == "test"
```

### 🎯 实践2：测试错误处理

```python
# ✅ 测试错误处理
async def test_vector_invalid_dimension(self):
    """测试无效向量维度"""
    store = FaissStore(VectorConfig(dimension=128))
    
    # 错误维度（64而不是128）
    vectors = [Vector(id="v1", values=[1.0] * 64)]
    
    # 应该抛出异常
    with pytest.raises((AssertionError, ValueError)):
        await store.add(vectors)
```

### 🎯 实践3：测试边界情况

```python
# ✅ 测试边界情况
async def test_cache_max_capacity(self):
    """测试缓存容量上限"""
    cache = MemoryCacheClient(CacheConfig(max_entries=10))
    
    # 添加到上限
    for i in range(10):
        await cache.set(f"key{i}", f"value{i}")
    
    # 添加第11个应该触发淘汰
    await cache.set("key_new", "value_new")
    
    # 验证最旧的被淘汰
    old_value = await cache.get("key0")
    assert old_value is None
    
    # 验证新的存在
    new_value = await cache.get("key_new")
    assert new_value == "value_new"
```

### 🎯 实践4：使用Mock模拟外部依赖

```python
# ✅ 使用Mock
from unittest.mock import AsyncMock, patch

async def test_kafka_publish(self):
    """测试Kafka发布消息（不需要真实Kafka）"""
    with patch('aiokafka.AioKafkaProducer') as mock_producer_class:
        # Mock生产者
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()
        
        # 创建客户端
        client = KafkaClient(config)
        
        # 发布消息
        await client.publish("test.topic", b"test message")
        
        # 验证调用了正确的方法
        mock_producer.send_and_wait.assert_called_once()
        args = mock_producer.send_and_wait.call_args
        assert args[0][0] == "test.topic"
```

### 🎯 实践5：使用Fixture共享测试数据

```python
# ✅ 使用Fixture
import pytest

@pytest.fixture
async def vector_store():
    """创建向量存储实例"""
    config = VectorConfig(type="faiss", dimension=128)
    store = FaissStore(config)
    
    # 添加初始数据
    vectors = [Vector(id=str(i), values=[1.0] * 128) for i in range(10)]
    await store.add(vectors)
    
    yield store
    
    # 清理
    await store.close()

async def test_search_with_fixture(vector_store):
    """使用Fixture测试"""
    results = await vector_store.search([1.0] * 128, top_k=5)
    assert len(results) > 0
```

---

## 常见错误

### ❌ 错误1：创建对象但不调用方法

```python
# ❌ 错误
def test_create_client(self):
    client = SomeClient(config)
    assert client is not None  # 证明不了任何功能！
```

**正确做法**：

```python
# ✅ 正确
async def test_client_functionality(self):
    client = SomeClient(config)
    await client.connect()  # 调用方法
    
    result = await client.execute("test command")  # 验证返回值
    assert result is not None
    assert result.status == "success"
```

### ❌ 错误2：使用hasattr验证方法存在

```python
# ❌ 错误
def test_has_methods(self):
    client = create_client(config)
    assert hasattr(client, "connect")  # 空方法也返回True！
    assert hasattr(client, "execute")   # 证明不了能工作！
```

**正确做法**：

```python
# ✅ 正确
async def test_methods_work(self):
    client = create_client(config)
    await client.connect()  # 真实调用connect
    
    result = await client.execute("test")  # 真实调用execute
    assert result.status == "success"  # 验证返回值
```

### ❌ 错误3：跳过集成测试而不是使用Mock

```python
# ❌ 错误
@pytest.mark.integration
async def test_kafka_integration(self):
    pytest.skip("Requires running Kafka")
    # 核心功能完全没有被测试！
```

**正确做法**：

```python
# ✅ 正确：单元测试使用Mock
async def test_kafka_with_mock(self):
    """不需要真实Kafka的单元测试"""
    with patch('aiokafka.AioKafkaProducer') as mock:
        producer = AsyncMock()
        mock.return_value = producer
        
        client = KafkaClient(config)
        await client.publish("topic", b"message")
        
        # 验证调用了真实方法
        producer.send_and_wait.assert_called_once()

# ✅ 正确：集成测试可选运行
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("KAFKA_HOST"), reason="需要KAFKA_HOST环境变量")
async def test_kafka_real_service(self):
    """需要真实服务的集成测试（可选）"""
    client = KafkaClient(config)
    await client.publish("topic", b"message")
    # 测试真实Kafka...
```

### ❌ 错误4：不验证返回值内容

```python
# ❌ 错误
def test_list_items(self):
    items = manager.list_items()
    assert len(items) > 0  # 空字典列表也能通过！
```

**正确做法**：

```python
# ✅ 正确
async def test_list_items(self):
    items = await manager.list_items()
    
    # 验证列表不为空
    assert len(items) > 0
    
    # 验证每个元素的结构
    assert all('id' in item for item in items)
    assert all('name' in item for item in items)
    
    # 验证具体值
    first_item = items[0]
    assert first_item['id'] == 'expected_id'
    assert first_item['name'] == 'expected_name'
```

---

## 测试模板

### 模板1：基础单元测试

```python
"""{模块名} 模块测试"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from infra.{module} import {Class}, Config


class Test{ClassName}:
    """测试类"""
    
    @pytest.fixture
    def config(self):
        """创建配置"""
        return Config(
            type="{type}",
            # 其他配置...
        )
    
    @pytest.mark.asyncio
    async def test_{method_name}(self, config):
        """测试{方法名}"""
        # 1. 创建实例
        client = {Class}(config)
        
        # 2. 调用方法
        result = await client.{method_name}(params)
        
        # 3. 验证返回值
        assert result is not None
        assert result.status == "expected_status"
        
    @pytest.mark.asyncio
    async def test_{method_name}_error_case(self, config):
        """测试错误处理"""
        client = {Class}(config)
        
        # 测试错误输入
        with pytest.raises(ValueError):
            await client.{method_name}(invalid_params)
```

### 模板2：Mock测试

```python
class Test{ClassName}WithMock:
    """使用Mock的测试"""
    
    @pytest.mark.asyncio
    async def test_{method}_with_mock(self):
        """测试{方法}（使用Mock）"""
        with patch('infra.{module}.{Client}') as mock_client_class:
            # 1. 设置Mock行为
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_client.method.return_value = {"result": "success"}
            
            # 2. 创建被测对象
            instance = {Class}(config)
            instance._client = mock_client
            instance._initialized = True
            
            # 3. 调用方法
            result = await instance.{method}(params)
            
            # 4. 验证返回值
            assert result["result"] == "success"
            
            # 5. 验证Mock被调用
            mock_client.method.assert_called_once_with(params)
```

### 模板3：异步测试

```python
class TestAsyncOperations:
    """异步操作测试"""
    
    @pytest.mark.asyncio
    async def test_async_method(self):
        """测试异步方法"""
        client = AsyncClient(config)
        
        # 真实异步调用
        result = await client.async_operation(data)
        
        # 验证结果
        assert result.status == "success"
        
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """测试并发操作"""
        client = AsyncClient(config)
        
        # 并发执行多个操作
        results = await asyncio.gather(
            client.operation("task1"),
            client.operation("task2"),
            client.operation("task3"),
        )
        
        # 验证所有操作成功
        assert all(r.status == "success" for r in results)
```

---

## 检查清单

### ✅ 测试前检查

- [ ] 确定要测试的方法/功能
- [ ] 确定是单元测试还是集成测试
- [ ] 确定是否需要Mock（外部依赖）
- [ ] 准备测试数据（正常、边界、错误）

### ✅ 测试中检查

- [ ] **真实调用方法**（不要只创建对象）
- [ ] **验证返回值内容**（不要只验证长度）
- [ ] **验证方法被调用**（如果是Mock测试）
- [ ] **测试错误处理**（异常情况）
- [ ] **测试边界情况**（边界值）

### ✅ 测试后检查

- [ ] 所有测试通过
- [ ] 没有跳过的测试（除非有明确理由）
- [ ] 测试覆盖率 > 80%
- [ ] 返回值验证完整
- [ ] 错误处理测试完整

### ✅ Mock测试检查

- [ ] Mock设置正确
- [ ] Mock返回值符合实际
- [ ] 验证Mock被正确调用
- [ ] Mock不会掩盖真实错误

---

## 示例参考

### ✅ 好的测试示例（Vector模块）

文件：`infra/tests/test_vector/test_client.py`

```python
class TestFaissStore:
    """FAISS 向量存储测试 - 使用真实实例"""
    
    @pytest.mark.asyncio
    async def test_faiss_add_vectors(self):
        """测试添加向量"""
        from infra.vector.faiss import FaissStore
        from infra.vector.schemas import Vector, VectorConfig
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 1. 创建测试数据
        vectors = [
            Vector(id="v1", values=[1.0] * 128, metadata={"type": "test"}),
            Vector(id="v2", values=[2.0] * 128, metadata={"type": "test"}),
        ]
        
        # 2. 真实调用方法
        ids = await store.add(vectors)
        
        # 3. 验证返回值
        assert len(ids) == 2  # ✅ 验证数量
        assert ids[0] == "v1"  # ✅ 验证具体值
        assert ids[1] == "v2"  # ✅ 验证具体值
    
    @pytest.mark.asyncio
    async def test_faiss_search_vectors(self):
        """测试向量搜索"""
        store = FaissStore(VectorConfig(type="faiss", dimension=128))
        
        # 添加测试数据
        await store.add([Vector(id="v1", values=[1.0] * 128, metadata={"key": "value"})])
        
        # 搜索向量
        results = await store.search([1.0] * 128, top_k=5)
        
        # 验证返回值
        assert len(results) > 0  # ✅ 验证返回了结果
        assert isinstance(results[0], SearchResult)  # ✅ 验证类型
        assert results[0].id == "v1"  # ✅ 验证具体值
        assert results[0].score >= 0.99  # ✅ 验证相似度
        assert results[0].metadata["key"] == "value"  # ✅ 验证元数据
```

### ✅ 好的Mock测试示例

```python
class TestMilvusStore:
    """Milvus 测试 - 使用Mock"""
    
    @pytest.mark.asyncio
    async def test_milvus_add_vectors(self):
        """测试添加向量到Milvus（不需要真实服务）"""
        from infra.vector.milvus import MilvusStore
        from unittest.mock import MagicMock, patch
        
        config = VectorConfig(type="milvus", dimension=128)
        
        # 1. Mock外部依赖
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            # 设置Mock行为
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_insert_result = MagicMock()
            mock_insert_result.insert_primary_keys = ["id1", "id2"]
            mock_client.insert.return_value = mock_insert_result
            
            # 2. 创建被测对象
            store = MilvusStore(config)
            store._client = mock_client
            store._collection_name = "test_collection"
            store._initialized = True
            
            # 3. 调用方法
            vectors = [
                Vector(id="id1", values=[1.0] * 128),
                Vector(id="id2", values=[2.0] * 128),
            ]
            ids = await store.add(vectors)
            
            # 4. 验证返回值
            assert len(ids) == 2
            assert "id1" in ids or "id2" in ids
            
            # 5. 验证Mock被调用
            mock_client.insert.assert_called_once()
```

---

## 总结

### 🎯 测试黄金法则

1. **真实调用方法** - 不要只创建对象
2. **验证返回值内容** - 不要只验证长度
3. **测试错误处理** - 不要只测试成功路径
4. **使用Mock替代跳过** - Mock外部依赖而不是跳过测试
5. **验证边界情况** - 测试上限、下限、空值、错误值

### 📚 参考资源

- [pytest官方文档](https://docs.pytest.org/)
- [unittest.mock文档](https://docs.python.org/3/library/unittest.mock.html)
- [AsyncMock文档](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.AsyncMock)

### 💡 问答

**Q: 什么时候用Mock？**  
A: 当需要外部服务（数据库、消息队列、API）但无法在单元测试中使用时。

**Q: Mock测试能替代集成测试吗？**  
A: 不能！Mock是单元测试，集成测试需要在CI/CD中可选运行。

**Q: 测试覆盖率要多少才够？**  
A: 核心模块建议 >85%，整体项目建议 >75%。

---

*最后更新: 2026-04-11  

---

## 证据索引（Evidence Index｜抽样）

- 单测/集成测试：`infra/tests/*`
**负责人**: AI Platform Team  
**状态**: 活跃文档
