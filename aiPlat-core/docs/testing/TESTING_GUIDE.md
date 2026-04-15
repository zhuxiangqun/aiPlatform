# aiPlat-core 框架层 - 测试指南

> 确保框架核心功能正确性的最佳实践

---

## 目录

- [测试原则](#测试原则)
- [模块优先级](#模块优先级)
- [测试分类](#测试分类)
- [最佳实践](#最佳实践)
- [常见错误](#常见错误)
- [测试模板](#测试模板)
- [检查清单](#检查清单)

---

## 测试原则

### 核心原则：**测试功能，而不是测试结构**

#### 好的测试 - 调用方法并验证返回值

```python
async def test_memory_store():
    """测试记忆存储功能"""
    # 1. 创建实例
    memory = MemoryStore(MemoryConfig(max_entries=100))
    
    # 2. 真实调用方法
    await memory.add("key1", "value1", {"metadata": "test"})
    
    # 3. 验证返回值
    result = await memory.get("key1")
    assert result is not None
    assert result.value == "value1"
    assert result.metadata["metadata"] == "test"
```

#### 测试覆盖率目标

| 模块层级 | 优先级 | 覆盖率目标 |
|---------|-------|-----------|
| P1: harness/integration, harness/execution, harness/memory | 高 | >85% |
| P2: harness/coordination, harness/knowledge | 中 | >80% |
| P3: harness/observability, harness/feedback_loops | 低 | >75% |

---

## 模块优先级

### P1 - 核心模块（最高优先级）

这些模块是框架的基础，必须优先测试：

- `harness/integration.py` - 统一入口
- `harness/execution/` - 执行系统
  - `engine.py` - 执行引擎
  - `langgraph/core.py` - LangGraph 编排
  - `langgraph/callbacks.py` - 回调系统
- `harness/memory/` - 记忆系统
  - `types.py` - 类型定义
  - `base.py` - 基础接口
  - `short_term.py` - 短期记忆
  - `long_term.py` - 长期记忆

### P2 - 重要模块

这些模块提供关键功能：

- `harness/coordination/` - 协调系统
  - `patterns/base.py` - 模式定义
  - `patterns/orchestrator.py` - 编排器
- `harness/knowledge/` - 知识系统
  - `types.py` - 类型定义
  - `retriever.py` - 知识检索
  - `indexer.py` - 知识索引

### P3 - 辅助模块

这些模块提供支持功能：

- `harness/observability/` - 观察系统
- `harness/feedback_loops/` - 反馈循环
- `harness/infrastructure/` - 基础设施

---

## 测试分类

### 单元测试（Unit Tests）

测试单个方法或函数的功能：

```python
class TestMemoryStore:
    """记忆存储单元测试"""
    
    @pytest.mark.asyncio
    async def test_add_memory(self):
        """测试添加记忆"""
        memory = ShortTermMemory(MemoryConfig(max_entries=100))
        
        # 调用方法
        result = await memory.add("key1", "value1")
        
        # 验证返回值
        assert result is True
        assert await memory.get("key1") == "value1"
```

### 集成测试（Integration Tests）

测试多个组件协作：

```python
@pytest.mark.integration
class TestHarnessIntegration:
    """框架集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """测试完整执行流程"""
        # 创建集成实例
        harness = HarnessIntegration(config)
        
        # 执行完整的Agent流程
        result = await harness.execute(
            agent_name="test_agent",
            input_data={"query": "test"}
        )
        
        # 验证完整结果
        assert result.status == "success"
        assert result.output is not None
```

### Mock测试

使用Mock模拟外部依赖：

```python
class TestLLMAdapter:
    """LLM适配器测试（使用Mock）"""
    
    @pytest.mark.asyncio
    async def test_llm_generate_with_mock(self):
        """测试LLM生成（Mock外部API）"""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            # 设置Mock行为
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="测试响应"))]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            # 测试方法
            adapter = OpenAIAdapter(LLMConfig(model="gpt-4"))
            result = await adapter.generate("测试提示")
            
            # 验证返回值
            assert result == "测试响应"
            
            # 验证Mock被调用
            mock_client.chat.completions.create.assert_called_once()
```

---

## 最佳实践

### 实践1: 测试接口实现

框架使用接口定义，需要测试各实现：

```python
class TestMemoryInterfaces:
    """测试记忆系统接口"""
    
    @pytest.mark.asyncio
    async def test_short_term_memory(self):
        """测试短期记忆实现"""
        memory = ShortTermMemory(MemoryConfig(max_entries=10))
        
        # 添加并验证
        await memory.add("key1", "value1")
        result = await memory.get("key1")
        
        assert result is not None
        assert result["value"] == "value1"
    
    @pytest.mark.asyncio
    async def test_long_term_memory(self):
        """测试长期记忆实现"""
        memory = LongTermMemory(MemoryConfig(persist=True))
        
        # 添加并验证
        await memory.add("key1", "value1", metadata={"type": "test"})
        result = await memory.get("key1")
        
        assert result is not None
        assert result["value"] == "value1"
        assert result["metadata"]["type"] == "test"
```

### 实践2: 测试协调模式

测试Agent协调模式：

```python
class TestCoordinationPatterns:
    """测试协调模式"""
    
    @pytest.mark.asyncio
    async def test_sequential_orchestrator(self):
        """测试顺序编排器"""
        orch = SequentialOrchestrator(config)
        
        # 添加步骤
        orch.add_step(step1)
        orch.add_step(step2)
        
        # 执行
        result = await orch.execute(input_data)
        
        # 验证执行顺序
        assert result.steps_executed == ["step1", "step2"]
        assert result.status == "completed"
```

### 实践3: 测试错误处理

```python
class TestErrorHandling:
    """测试错误处理"""
    
    @pytest.mark.asyncio
    async def test_invalid_input(self):
        """测试无效输入"""
        engine = ExecutionEngine(config)
        
        # 测试错误输入
        with pytest.raises(ValueError):
            await engine.execute(None)
    
    @pytest.mark.asyncio
    async def test_execution_failure(self):
        """测试执行失败"""
        engine = ExecutionEngine(config)
        
        # 模拟失败
        with patch.object(engine, '_run_step', side_effect=Exception("失败")):
            result = await engine.execute(input_data)
            
            assert result.status == "failed"
            assert "失败" in result.error
```

### 实践4: 测试异步操作

```python
class TestAsyncOperations:
    """测试异步操作"""
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """测试并发操作"""
        memory = ShortTermMemory(MemoryConfig(max_entries=100))
        
        # 并发执行多个操作
        await asyncio.gather(
            memory.add("key1", "value1"),
            memory.add("key2", "value2"),
            memory.add("key3", "value3"),
        )
        
        # 验证所有操作成功
        assert await memory.get("key1") is not None
        assert await memory.get("key2") is not None
        assert await memory.get("key3") is not None
```

### 实践5: 使用Fixture共享测试数据

```python
import pytest

@pytest.fixture
async def harness():
    """创建框架实例"""
    config = HarnessConfig(
        memory=MemoryConfig(max_entries=100),
        execution=ExecutionConfig(timeout=30)
    )
    harness = HarnessIntegration(config)
    await harness.initialize()
    
    yield harness
    
    await harness.cleanup()

class TestHarness:
    """使用Fixture测试"""
    
    async def test_execute_with_fixture(self, harness):
        """使用Fixture测试执行"""
        result = await harness.execute(
            agent_name="test_agent",
            input_data={"query": "test"}
        )
        
        assert result.status == "success"
```

---

## 常见错误

### 错误1：只创建对象不调用方法

```python
# 错误
def test_memory():
    memory = ShortTermMemory(config)
    assert memory is not None  # 这证明不了任何功能！

# 正确
async def test_memory():
    memory = ShortTermMemory(config)
    await memory.add("key1", "value1")  # 调用方法
    result = await memory.get("key1")    # 验证返回值
    assert result == "value1"
```

### 错误2：使用hasattr验证方法存在

```python
# 错误
def test_interface():
    memory = create_memory(config)
    assert hasattr(memory, "add")  # 空方法也返回True！

# 正确
async def test_interface():
    memory = create_memory(config)
    result = await memory.add("key1", "value1")  # 真实调用
    assert result is True  # 验证返回值
```

### 错误3：不验证返回值内容

```python
# 错误
async def test_search():
    results = await knowledge.search("query")
    assert len(results) > 0  # 空字典也能通过！

# 正确
async def test_search():
    results = await knowledge.search("query")
    assert len(results) > 0
    assert results[0].id is not None  # 验证内容
    assert results[0].content is not None
```

---

## 测试模板

### 模板1：框架核心模块测试

```python
"""{module_name} 模块测试"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from harness.{module} import {Class}, Config


class Test{ClassName}:
    """{class_name} 测试类"""
    
    @pytest.fixture
    def config(self):
        """创建配置"""
        return Config(
            param1="value1",
            param2="value2",
        )
    
    @pytest.mark.asyncio
    async def test_{method_name}(self, config):
        """测试{方法名}"""
        # 1. 创建实例
        instance = {Class}(config)
        
        # 2. 调用方法
        result = await instance.{method_name}(params)
        
        # 3. 验证返回值
        assert result is not None
        assert result.status == "success"
```

### 模板2：接口实现测试

```python
"""测试接口的不同实现"""

import pytest
from harness.{module}.interfaces import {Interface}
from harness.{module}.impl1 import {Impl1}
from harness.{module}.impl2 import {Impl2}


class Test{Interface}Implementations:
    """测试接口实现"""
    
    @pytest.fixture(params=[{Impl1}, {Impl2}])
    def implementation(self, request):
        """参数化测试不同实现"""
        return request.param
    
    @pytest.mark.asyncio
    async def test_interface_method(self, implementation):
        """测试接口方法"""
        instance = implementation(config)
        
        # 测试接口方法
        result = await instance.interface_method(params)
        
        # 验证返回值
        assert result is not None
        assert hasattr(result, 'required_field')
```

### 模板3：集成测试

```python
"""集成测试"""

import pytest
from harness.integration import HarnessIntegration
from harness.config import HarnessConfig


@pytest.mark.integration
class TestIntegration:
    """集成测试"""
    
    @pytest.fixture
    async def harness(self):
        """创建完整框架实例"""
        config = HarnessConfig()
        harness = HarnessIntegration(config)
        await harness.initialize()
        yield harness
        await harness.cleanup()
    
    @pytest.mark.asyncio
    async def test_full_flow(self, harness):
        """测试完整流程"""
        # 执行完整流程
        result = await harness.execute(
            agent_name="test_agent",
            input_data={"query": "test"}
        )
        
        # 验证完整性
        assert result.status == "success"
        assert result.output is not None
```

---

## 检查清单

### 编写测试前

- [ ] 确定要测试的方法/功能
- [ ] 理解方法的预期行为
- [ ] 确定测试类型（单元/集成/Mock）
- [ ] 准备测试数据（正常、边界、错误）

### 编写测试时

- [ ] **真实调用方法**（不要只创建对象）
- [ ] **验证返回值内容**（不要只验证长度）
- [ ] **测试接口实现**（如果有多个实现）
- [ ] **测试错误处理**（异常情况）
- [ ] **测试边界情况**（边界值）

### 测试后检查

- [ ] 所有测试通过
- [ ] 没有无故跳过的测试
- [ ] 测试覆盖率达标
- [ ] 返回值验证完整
- [ ] 错误处理测试完整

### Mock测试检查

- [ ] Mock设置正确
- [ ] Mock返回值符合实际
- [ ] 验证Mock被正确调用
- [ ] Mock不会掩盖真实错误

---

## 测试目录结构

```
aiPlat-core/tests/
├── unit/                    # 单元测试
│   ├── test_harness/
│   │   ├── test_integration.py
│   │   ├── test_execution/
│   │   │   ├── test_engine.py
│   │   │   └── test_langgraph/
│   │   │       ├── test_core.py
│   │   │       └── test_callbacks.py
│   │   ├── test_memory/
│   │   │   ├── test_types.py
│   │   │   ├── test_base.py
│   │   │   ├── test_short_term.py
│   │   │   └── test_long_term.py
│   │   ├── test_coordination/
│   │   │   └── test_patterns.py
│   │   └── test_knowledge/
│   │       ├── test_types.py
│   │       ├── test_retriever.py
│   │       └── test_indexer.py
│   └── test_adapters/
│       └── test_llm/
│           └── test_base.py
├── integration/             # 集成测试
│   └── test_harness_full.py
└── conftest.py              # pytest配置和fixtures
```

---

## 参考资源

- [pytest官方文档](https://docs.pytest.org/)
- [unittest.mock文档](https://docs.python.org/3/library/unittest.mock.html)
- [pytest-asyncio文档](https://pytest-asyncio.readthedocs.io/)

---

*最后更新: 2026-04-14*
**负责人**: AI Platform Team
**状态**: 活跃文档