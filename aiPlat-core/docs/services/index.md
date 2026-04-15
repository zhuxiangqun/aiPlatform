# Core Services 模块

> 提供 aiPlat-core 的核心基础服务

---

## 模块概述

Core Services 模块提供 aiPlat-core 所需的基础服务能力，是其他模块的公共依赖。

### 服务组件

| 服务 | 说明 | 状态 |
|------|------|------|
| **PromptService** | 提示词模板管理与渲染 | ✅ 已实现 |
| **ModelService** | 模型调用统一封装，含 FormatAffinity | ✅ 已实现 |
| **TraceService** | 执行链路追踪与指标，含 DecayType | ✅ 已实现 |
| **ContextService** | 会话上下文管理，含 File-based Communication | ✅ 已实现 |
| **FileService** | Agent 间文件化通信管理 | ✅ 已实现 |

---

## PromptService

### 功能特性

- 提示词模板注册与存储
- 变量替换与渲染
- 版本控制
- 模板验证
- 缓存优化

### 使用示例

```python
from core.services import PromptService

# 创建服务实例
prompt_service = PromptService()

# 注册模板
await prompt_service.register_template(
    template_id="chat-template",
    name="Chat Template",
    template="You are a helpful assistant. User: {user_input}",
    metadata={"category": "chat"}
)

# 渲染模板
prompt = await prompt_service.render(
    template_id="chat-template",
    variables={"user_input": "Hello!"}
)

# 更新模板
await prompt_service.update_template(
    template_id="chat-template",
    template="You are a {role}. User: {user_input}",
    increment_version=True
)

# 获取模板版本
versions = await prompt_service.get_versions("chat-template")
```

### API 参考

|方法 | 说明 |
|------|------|
| `register_template()` | 注册新模板 |
| `get_template()` | 获取模板 |
| `render()` | 渲染模板 |
| `update_template()` | 更新模板 |
| `delete_template()` | 删除模板 |
| `list_templates()` | 列出所有模板 |
| `get_versions()` | 获取模板版本列表 |

---

## ModelService

### 功能特性

- 模型注册与发现
- 统一调用接口
- 配置管理
- 成本追踪
- 重试与降级策略

### 使用示例

```python
from core.services import ModelService, ModelConfig, ModelProvider

# 创建服务实例
model_service = ModelService()

# 注册模型
config = ModelConfig(
    model_id="gpt-4",
    provider=ModelProvider.OPENAI,
    model_name="gpt-4",
    api_key="sk-...",
    temperature=0.7,
    max_tokens=4096
)
await model_service.register_model(config, set_default=True)

# 调用模型
response = await model_service.call(
    model_id="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)

# 获取统计信息
stats = await model_service.get_stats(model_id="gpt-4")
```

### 支持的提供商

| 提供商 |枚举值 | 说明 |
|--------|--------|------|
| OpenAI | `OPENAI` | GPT系列模型 |
| Anthropic | `ANTHROPIC` | Claude 系列模型 |
| Ollama | `LOCAL_OLLAMA` | 本地 Ollama |
| vLLM | `LOCAL_VLLM` | 本地 vLLM |
| Custom | `CUSTOM` | 自定义模型 |

### API 参考

| 方法 | 说明 |
|------|------|
| `register_model()` | 注册模型 |
| `get_model()` | 获取模型配置 |
| `list_models()` | 列出模型 |
| `set_default_model()` | 设置默认模型 |
| `get_default_model()` | 获取默认模型 |
| `call()` | 调用模型 |
| `get_call_history()` | 获取调用历史 |
| `get_stats()` | 获取统计信息 |

---

## TraceService

### 功能特性

- 执行链路追踪
- 性能指标采集
- Span 管理
- 分布式追踪支持
- 追踪查询与分析

### 使用示例

```python
from core.services import TraceService

# 创建服务实例
trace_service = TraceService()

# 开始追踪
trace = await trace_service.start_trace(
    name="agent-execution",
    attributes={"agent_id": "agent-001"}
)

# 开始 Span
span = await trace_service.start_span(
    trace_id=trace.trace_id,
    name="tool-call",
    attributes={"tool": "web-search"}
)

# 添加事件
await trace_service.add_span_event(
    span_id=span.span_id,
    event_name="tool-started",
    attributes={"query": "weather"}
)

# 结束 Span
await trace_service.end_span(span.span_id)

# 结束追踪
await trace_service.end_trace(trace.trace_id)

# 获取统计
stats = await trace_service.get_stats()
```

### Span 状态

| 状态 | 说明 |
|------|------|
| `STARTED` | 已开始 |
| `RUNNING` | 运行中 |
| `SUCCESS` | 成功 |
| `FAILED` | 失败 |
| `TIMEOUT` | 超时 |

### API 参考

| 方法 | 说明 |
|------|------|
| `start_trace()` | 开始追踪 |
| `end_trace()` | 结束追踪 |
| `start_span()` | 开始 Span |
| `end_span()` | 结束 Span |
| `add_span_event()` | 添加事件 |
| `set_span_attribute()` | 设置属性 |
| `get_trace()` | 获取追踪 |
| `get_span()` | 获取 Span |
| `list_traces()` | 列出追踪 |
| `get_trace_spans()` | 获取追踪的所有 Span |
| `get_stats()` | 获取统计 |
| `export_trace()` | 导出追踪 |

---

## ContextService

### 功能特性

- 会话上下文管理
- 状态持久化
- 上下文共享
- 生命周期管理
- 上下文查询与检索

### 使用示例

```python
from core.services import ContextService

# 创建服务实例
context_service = ContextService(default_ttl=3600)

# 创建上下文
context = await context_service.create_context(
    user_id="user-001",
    agent_id="agent-001",
    data={"language": "zh", "mode": "chat"},
    metadata={"source": "web"}
)

# 设置值
await context_service.set_context_value(
    session_id=context.session_id,
    key="current_topic",
    value="AI"
)

# 获取值
topic = await context_service.get_context_value(
    session_id=context.session_id,
    key="current_topic",
    default="unknown"
)

# 更新上下文
await context_service.update_context(
    session_id=context.session_id,
    data={"language": "en"},
    merge=True
)

# 导出上下文
json_data = await context_service.export_context(context.session_id)

# 获取统计
stats = await context_service.get_stats()
```

### 上下文状态

| 状态 | 说明 |
|------|------|
| `ACTIVE` | 活跃 |
| `IDLE` | 空闲 |
| `EXPIRED` | 已过期 |
| `CLOSED` | 已关闭 |

### API 参考

| 方法 | 说明 |
|------|------|
| `create_context()` | 创建上下文 |
| `get_context()` | 获取上下文 |
| `update_context()` | 更新上下文 |
| `set_context_value()` | 设置值 |
| `get_context_value()` | 获取值 |
| `delete_context()` | 删除上下文 |
| `list_user_contexts()` | 列出用户上下文 |
| `list_agent_contexts()` | 列出 Agent 上下文 |
| `close_context()` | 关闭上下文 |
| `expire_context()` | 过期上下文 |
| `extend_context_ttl()` | 延长 TTL |
| `export_context()` | 导出上下文 |
| `import_context()` | 导入上下文 |
| `get_stats()` | 获取统计 |

---

## FileService

### 功能特性

- Agent 间文件化通信管理
- 文件生命周期管理（创建、读取、更新、删除）
- 文件模板和自动填充
- 版本控制和差异对比
- 支持 spec.md / sprint-report.md / feedback.md / handoff.md 等类型

### 使用示例

```python
from core.services import FileService

file_service = FileService()

# 创建文件
file = await file_service.create_file(
    agent_id="agent-001",
    file_type="spec",
    content="# Requirements\n\n## Feature A\n...",
    metadata={"project": "aiPlat"}
)

# 获取文件
file = await file_service.get_file(file_id=file.file_id)

# 更新文件
updated = await file_service.update_file(
    file_id=file.file_id,
    content="# Updated Requirements\n\n## Feature A\n...",
    increment_version=True
)

# 列出 Agent 的文件
files = await file_service.list_agent_files(agent_id="agent-001")
```

### ContextFile 文件类型

| 文件类型 | 枚举值 | 用途 |
|---------|--------|------|
| **需求规格** | `SPEC` | 功能需求、性能指标 |
| **冲刺报告** | `SPRINT_REPORT` | 完成情况、问题 |
| **反馈记录** | `FEEDBACK` | 问题描述、修复建议 |
| **交接文档** | `HANDOFF` | 当前状态、后续任务 |
| **评审记录** | `REVIEW` | 评审意见、修改要求 |

### API 参考

| 方法 | 说明 |
|------|------|
| `create_file()` | 创建文件 |
| `get_file()` | 获取文件 |
| `update_file()` | 更新文件 |
| `delete_file()` | 删除文件 |
| `list_agent_files()` | 列出 Agent 的文件 |
| `get_file_versions()` | 获取文件版本列表 |
| `get_stats()` | 获取统计 |

---

## FormatAffinity（格式亲和性）

ModelService 内置格式亲和性分析能力：

| 维度 | 说明 | 影响 |
|------|------|------|
| **结构亲和性** | 对特定输出结构的偏好 | JSON > Markdown > 纯文本 |
| **风格亲和性** | 对语言风格的偏好 | 简洁 > 冗长、正式 > 口语 |
| **长度亲和性** | 对输出长度的偏好 | 适中对齐模型上下文窗口 |
| **示例亲和性** | 对 Few-shot 示例的响应 | 有示例 > 无示例 |

### 格式优化策略

| 策略 | 枚举值 | 说明 |
|------|--------|------|
| **格式锁定** | `FORMAT_LOCK` | 固定输出格式，减少变化 |
| **格式渐进** | `FORMAT_PROGRESSIVE` | 从简单到复杂递进 |
| **格式反馈** | `FORMAT_FEEDBACK` | 根据执行结果调整格式 |
| **格式模板** | `FORMAT_TEMPLATE` | 提供标准化模板 |

---

## DecayType（价值衰减类型）

TraceService 内置价值衰减追踪能力：

| 衰减类型 | 枚举值 | 衰减速率 | 说明 |
|---------|--------|---------|------|
| **格式亲和性** | `FORMAT_AFFINITY` | 最快 | 模型对格式敏感，格式变化导致参考价值下降 |
| **能力互补** | `CAPABILITY_COMPLEMENT` | 中等 | 能力边界随模型升级变化 |
| **反馈质量** | `FEEDBACK_QUALITY` | 最慢 | 核心反馈原则长期有效 |

---

## 设计原则

### 服务独立性

每个服务都是独立的，不依赖其他服务：

- **PromptService**：仅依赖标准库
- **ModelService**：不依赖具体模型实现，通过适配器调用
- **TraceService**：独立的追踪系统
- **ContextService**：独立的上下文管理
- **FileService**：独立的文件通信管理

### 服务边界

**服务提供**：
- 基础能力抽象
- 统一接口定义
- 状态管理
- 配置管理

**服务不提供**：
- 业务逻辑（放 agents/skills）
- 数据存储（放 memory/knowledge）
- 工具实现（放 tools）
- 工作流定义（放 orchestration）

### 临时替代方案

在 services 模块实现前，相关功能由以下模块提供：

| 服务 | 临时位置 |
|------|----------|
| Prompt管理 | `harness/infrastructure/` |
| Model调用 | `adapters/llm/` |
| 追踪服务 | `harness/observability/` |
| 上下文管理 | `harness/execution/` |

现在这些功能已统一到 `services/` 模块。

---

## 模块依赖

```
services/
├── 不依赖任何aiPlat-core 内部模块
├── 仅依赖标准库和数据类
└── 可被所有核心模块使用

依赖关系：
harness/ ------> services/
agents/ --------> services/
skills/ --------> services/
memory/ --------> services/
knowledge/ -----> services/
tools/ ---------> services/
```

---

## 性能考虑

### 内存使用

- 模板和上下文数据默认存储在内存中
- 生产环境建议使用外部存储（Redis、数据库）
- 可通过继承扩展实现持久化

### 并发处理

- 所有方法都是异步的（`async`）
- 支持并发调用
- 无状态设计，线程安全

### 缓存策略

- PromptService 内置模板缓存
- ModelService 维护调用历史
- TraceService 维护追踪缓存
- ContextService 维护上下文缓存

---

## 扩展指南

### 扩展存储

```python
from core.services import PromptService

class PersistentPromptService(PromptService):
    """支持持久化的 PromptService"""
    
    def __init__(self, db_client):
        super().__init__()
        self.db_client = db_client
    
    async def register_template(self, ...):
        template = await super().register_template(...)
        await self.db_client.save_template(template)
        return template
```

### 扩展模型调用

```python
from core.services import ModelService

class CustomModelService(ModelService):
    """支持自定义模型的 ModelService"""
    
    async def _call_provider(self, config, ...):
        if config.provider == ModelProvider.CUSTOM:
            # 实现自定义模型调用
            return await self._call_custom_model(config, ...)
        return await super()._call_provider(config, ...)
```

---

## 相关文档

- [架构总览](../architecture/index.md) - 整体架构设计
- [harness 模块](../harness/index.md) - 执行引擎
- [apps 模块](../apps/index.md) - 应用层实现

---

*最后更新: 2026-04-14*
**版本**: v1.1
**维护团队**: AI Platform Team