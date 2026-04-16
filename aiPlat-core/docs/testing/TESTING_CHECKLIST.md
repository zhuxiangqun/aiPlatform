# 测试检查清单（设计真值：以代码事实为准）

> 说明：本清单为测试质量基线，适用于 core 与 infra 的测试贡献。

> 快速检查测试是否合格

---

## 编写测试前

- [ ] 确定要测试的方法
- [ ] 理解方法的预期行为
- [ ] 确定需要的测试类型（单元/集成/Mock）
- [ ] 准备测试数据（正常、边界、错误）

---

## 编写测试时

### 必须项

- [ ] **真实调用方法**（不要只创建对象）
  ```python
  # 错误
  harness = HarnessIntegration(config)
  assert harness is not None
  
  # 正确
  harness = HarnessIntegration(config)
  result = await harness.execute(agent_name="test", input_data={})
  assert result.status == "success"
  ```

- [ ] **验证返回值内容**（不要只验证长度）
  ```python
  # 错误
  results = await memory.search("query")
  assert len(results) > 0
  
  # 正确
  results = await memory.search("query")
  assert len(results) > 0
  assert results[0].id is not None
  assert results[0].content is not None
  ```

- [ ] **至少一个断言验证返回值内容**
  ```python
  # 必须有
  assert result.field1 == value1
  assert result.field2 == value2
  ```

- [ ] **测试方法名描述清晰**
  ```python
  # 好的命名
  async def test_memory_add_returns_correct_value()
  
  # 差的命名
  async def test_add()
  ```

---

## Mock测试

### 必须项

- [ ] Mock设置完整
  ```python
  # 完整的Mock设置
  with patch('openai.AsyncOpenAI') as mock_client_class:
      mock_client = MagicMock()
      mock_client_class.return_value = mock_client
      mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
  ```

- [ ] 验证Mock被调用
  ```python
  # 验证Mock调用
  mock_client.method.assert_called_once_with(params)
  ```

- [ ] Mock返回值符合实际

### 禁止项

- [ ] 不要Mock被测对象本身
- [ ] 不要过度Mock简单的数据结构
- [ ] 不要用Mock替代集成测试

---

## 异步测试

### 必须项

- [ ] 使用`@pytest.mark.asyncio`
- [ ] 使用`async/await`调用异步方法
  ```python
  @pytest.mark.asyncio
  async def test_async_method():
      result = await memory.add("key", "value")
      assert result is True
  ```

---

## 错误处理测试

- [ ] 测试异常情况
  ```python
  with pytest.raises(ValueError):
      await engine.execute(None)
  ```

- [ ] 测试边界值
  ```python
  # 测试上限
  result = await memory.add("key", "x" * max_length)
  
  # 测试下限
  result = await memory.add("key", "")
  
  # 测试边界外
  with pytest.raises(ValueError):
      await memory.add("key", "x" * (max_length + 1))
  ```

---

## 测试后检查

- [ ] 所有测试通过
- [ ] 没有无故跳过的测试
- [ ] 测试覆盖率达标（P1 >85%, P2 >80%, P3 >75%）
- [ ] 返回值验证完整
- [ ] 方法调用正确

---

## 常见错误

### 错误1：只创建对象

```python
# 错误
def test_harness():
    harness = HarnessIntegration(config)
    assert harness is not None  # 这什么都没测试！

# 正确
async def test_harness():
    harness = HarnessIntegration(config)
    await harness.initialize()
    result = await harness.execute(agent_name="test", input_data={})
    assert result.status == "success"
```

### 错误2：使用hasattr

```python
# 错误
def test_interface():
    memory = create_memory(config)
    assert hasattr(memory, "add")  # 空方法也返回True！

# 正确
async def test_interface():
    memory = create_memory(config)
    result = await memory.add("key", "value")
    assert result is True
```

### 错误3：不验证返回值

```python
# 错误
async def test_list_items():
    items = await knowledge.list_items()
    assert len(items) > 0  # 空字典也能通过！

# 正确
async def test_list_items():
    items = await knowledge.list_items()
    assert len(items) > 0
    assert items[0].id is not None
    assert items[0].content is not None
```

---

## 正确示例

```python
@pytest.mark.asyncio
async def test_correct_example():
    """好的测试示例"""
    # 1. 创建实例
    memory = ShortTermMemory(MemoryConfig(max_entries=100))
    
    # 2. 真实调用方法
    result = await memory.add("key1", "value1")
    
    # 3. 验证返回值内容
    assert result is True
    
    # 4. 验证副作用
    value = await memory.get("key1")
    assert value == "value1"
    
    # 5. 验证其他相关操作
    all_keys = await memory.list_keys()
    assert "key1" in all_keys
```

---

## 快速参考

```python
# 单元测试模板
class TestFeature:
    @pytest.mark.asyncio
    async def test_method_success(self):
        instance = Class(config)
        result = await instance.method(params)
        assert result.status == "success"

# Mock测试模板
class TestFeatureWithMock:
    @pytest.mark.asyncio
    async def test_method_with_mock(self):
        with patch('module.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.method.return_value = expected_result
            
            result = await instance.method(params)
            
            assert result.status == "success"
            mock_client.method.assert_called_once()
```

---

*最后更新: 2026-04-14*
**查看详细**: [TESTING_GUIDE.md](./TESTING_GUIDE.md)
