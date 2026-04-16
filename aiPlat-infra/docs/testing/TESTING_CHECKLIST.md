# 测试检查清单（设计真值：以代码事实为准）

> 说明：本清单为 infra 测试质量基线，适用于 `infra/tests/*` 的单测/集成测试贡献。

> 快速检查测试是否合格

---

## ✅ 编写测试前

- [ ] 确定要测试的方法
- [ ] 理解方法的预期行为
- [ ] 确定需要的测试类型（单元/集成/Mock）
- [ ] 准备测试数据（正常、边界、错误）

---

## ✅ 编写测试时

### 必须项

- [ ] **真实调用方法**（不要只创建对象）
  ```python
  # ❌ 错误
  client = SomeClient(config)
  assert client is not None
  
  # ✅ 正确
  client = SomeClient(config)
  result = await client.method(params)
  assert result.status == "success"
  ```

- [ ] **验证返回值内容**（不要只验证长度）
  ```python
  # ❌ 错误
  items = await client.list_items()
  assert len(items) > 0
  
  # ✅ 正确
  items = await client.list_items()
  assert len(items) > 0
  assert items[0]['id'] == 'expected_id'
  assert items[0]['name'] == 'expected_name'
  ```

- [ ] **至少一个断言验证返回值内容**
  ```python
  # ✅ 必须有
  assert result.field1 == value1
  assert result.field2 == value2
  ```

- [ ] **测试方法名描述清晰**
  ```python
  # ✅ 好的命名
  def test_add_vectors_returns_correct_ids(self):
  
  # ❌ 差的命名
  def test_add(self):
  ```

---

## ✅ Mock测试

### 必须项

- [ ] Mock设置完整
  ```python
  # ✅ 完整的Mock设置
  with patch('module.ClientClass') as mock_client_class:
      mock_client = MagicMock()
      mock_client_class.return_value = mock_client
      mock_client.method.return_value = expected_result
  ```

- [ ] 验证Mock被调用
  ```python
  # ✅ 验证Mock调用
  mock_client.method.assert_called_once_with(params)
  ```

- [ ] Mock返回值符合实际

### 禁止项

- [ ] 不要Mock被测对象本身
- [ ] 不要过度Mock简单的数据结构
- [ ] 不要用Mock替代集成测试

---

## ✅ 异步测试

### 必须项

- [ ] 使用`@pytest.mark.asyncio`
- [ ] 使用`async/await`调用异步方法
  ```python
  @pytest.mark.asyncio
  async def test_async_method(self):
      result = await client.async_method()
      assert result.status == "success"
  ```

---

## ✅ 错误处理测试

- [ ] 测试异常情况
  ```python
  with pytest.raises(ValueError):
      await client.method(invalid_params)
  ```

- [ ] 测试边界值
  ```python
  # 测试上限
  result = await client.method(max_value)
  
  # 测试下限
  result = await client.method(min_value)
  
  # 测试边界外
  with pytest.raises(ValueError):
      await client.method(max_value + 1)
  ```

---

## ✅ 测试后检查

- [ ] 所有测试通过
- [ ] 没有无故跳过的测试
- [ ] 测试覆盖率 > 80%
- [ ] 返回值验证完整
- [ ] 方法调用正确

---

## ❌ 常见错误

### 错误1：只创建对象

```python
# ❌ 错误
def test_client(self):
    client = SomeClient(config)
    assert client is not None  # 这什么都没测试！
```

### 错误2：使用hasattr

```python
# ❌ 错误
def test_has_methods(self):
    client = create_client(config)
    assert hasattr(client, "connect")  # 空方法也返回True！
```

### 错误3：跳过集成测试

```python
# ❌ 错误
@pytest.mark.integration
async def test_real_service(self):
    pytest.skip("Requires running service")  # 应该用Mock！
```

### 错误4：不验证返回值

```python
# ❌ 错误
def test_list_items(self):
    items = manager.list_items()
    assert len(items) > 0  # 空字典也能通过！
```

---

## ✅ 正确示例

```python
@pytest.mark.asyncio
async def test_correct_example(self):
    """好的测试示例"""
    # 1. 创建实例
    client = SomeClient(config)
    
    # 2. 真实调用方法
    result = await client.method(test_params)
    
    # 3. 验证返回值内容
    assert result is not None
    assert result.status == "success"
    assert result.data.field == "expected_value"
    
    # 4. 验证副作用（如果有）
    # 例如：验证数据已保存、缓存已更新等
```

---

## 📚 快速参考

```python
# 单元测试模板
class TestFeature:
    @pytest.mark.asyncio
    async def test_method_success(self):
        client = Client(config)
        result = await client.method(params)
        assert result.status == "success"

# Mock测试模板
class TestFeatureWithMock:
    @pytest.mark.asyncio
    async def test_method_with_mock(self):
        with patch('module.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            result = await client.method(params)
            
            assert result.status == "success"
            mock_client.some_method.assert_called_once()
```

---

*最后更新: 2026-04-11  

---

## 证据索引（Evidence Index｜抽样）

- 测试目录：`infra/tests/*`
**查看详细**: [TESTING_GUIDE.md](./TESTING_GUIDE.md)
