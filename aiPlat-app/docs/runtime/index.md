# 运行时模块

> 运行时模块是 AI Platform 应用层的核心执行引擎，负责 Agent Loop 的完整实现，包括 Reason → Act → Observe 循环、工具调用、记忆管理和 TokMem 集成。

---

## 一、模块定位

### 1.1 核心职责

运行时模块在整个 AI Platform 架构中承担以下核心职责：

| 职责 | 说明 |
|------|------|
| **Agent Loop** | 实现 Reason → Act → Observe 完整循环 |
| **LLM 集成** | 对接多种 LLM 提供商 (DeepSeek/OpenAI/Anthropic) |
| **工具执行** | 管理工具注册、调用、超时控制 |
| **记忆管理** | 会话级上下文记忆管理 |
| **TokMem 集成** | Tool Token Memory 智能工具推荐 |

### 1.2 与相邻模块的关系

```
┌─────────────────────────────────────────────────────────────┐
│                       Gateway                               │
│  ┌─────────────┐  ┌─────────────────────┐  ┌───────────┐  │
│  │  Router    │  │  Intent Parser        │  │  Session  │  │
│  └─────────────┘  └─────────────────────┘  └───────────┘  │
└────────────────────────────┬────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Runtime                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │  Reason    │  │  Act       │  │  Observe            │   │
│  │  (思考)    │  │  (行动)    │  │  (观察)            │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│  ┌─────────────────────┐  ┌───────────────────────────────┐   │
│  │  LLM Integration    │  │  Tool Registry               │   │
│  │  (LLM 集成)          │  │  (工具注册)                   │   │
│  └─────────────────────┘  └───────────────────────────────┘   │
│  ┌─────────────────────┐  ┌───────────────────────────────┐   │
│  │  Session Memory     │  │  TokMem                        │   │
│  │  (会话记忆)          │  │  (工具Token记忆)                │   │
│  └─────────────────────┘  └───────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
               ┌─���────────────┼──────────────┐
               ▼              ▼              ▼
┌─────────────────────┐ ┌─────────────┐ ┌─────────────────────────┐
│    Events           │ │  Tools      │ │    LLM Providers       │
│    (事件总线)       │ │  (工具集)    │ │    (LLM 提供商)         │
└─────────────────────┘ └─────────────┘ └─────────────────────────┘
```

---

## 二、核心概念定义

### 2.1 Agent 状态机

Agent 运行时具有一个完整的状态机，用于控制执行过程：

```python
class AgentStatus(Enum):
    """Agent 运行状态"""
    IDLE = "idle"           # 空闲
    THINKING = "thinking"   # 思考中 (Reason)
    ACTING = "acting"       # 行动中 (Act)
    OBSERVING = "observing" # 观察中 (Observe)
    COMPLETED = "completed" # 完成
    ERROR = "error"         # 错误
```

**状态转换图**：

```
IDLE ──process()──► THINKING ── Act ── OBSERVING ── COMPLETED
    ▲              │             │            │
    │              │             │            │
    └──────────────┴─────────────┴────────────┘
                (循环回到 THINKING)
                            │
                            ▼
                          ERROR
```

### 2.2 AgentConfig 配置

```python
@dataclass
class AgentConfig:
    """Agent 配置"""
    model_provider: str = "deepseek"       # 模型提供商
    model_name: str = "deepseek-chat"   # 模型名称
    temperature: float = 0.7             # 温度参数
    max_tokens: int = 4096              # 最大输出Token

    max_tool_calls: int = 10             # 最大工具调用次数
    tool_timeout: int = 30               # 工具执行超时(秒)

    max_iterations: int = 10             # 最大迭代次数
    enable_thinking: bool = True         # 是否启用思考过程

    memory_enabled: bool = True          # 启用记忆功能
    context_window: int = 10              # 上下文窗口大小

    tokmem_enabled: bool = True          # 启用 TokMem
    tokmem_recall_mode: str = "hybrid"   # TokMem 召回模式
    tokmem_top_k: int = 5                # TokMem Top-K
```

### 2.3 AgentRequest/AgentResponse

```python
@dataclass
class AgentRequest:
    """Agent 请求"""
    user_input: str              # 用户输入
    user_id: str                 # 用户ID
    session_id: str              # 会话ID
    channel: str                 # 渠道
    context: dict               # 扩展上下文


@dataclass
class AgentResponse:
    """Agent 响应"""
    content: str                 # 响应内容
    status: AgentStatus          # 执行状态
    tool_calls: list[dict]       # 工具调用列表
    thinking: str = ""           # 思考过程
    metadata: dict = field(default_factory=dict)  # 元数据
```

### 2.4 Thought 结构

Agent Loop 中每个迭代产生的思考结构：

```python
@dataclass
class Thought:
    """思考结构"""
    thought: str                 # 思考内容
    thinking: str = ""           # 思考过程 (如果启用)
    action: Optional[dict] = None # 行动指令
    # action 结构: {"tool": "tool_name", "args": {...}}
```

---

## 三、配置结构

### 3.1 运行时配置

```yaml
# aiPlat-app/runtime/config.yaml

runtime:
  # ==================== 模型配置 ====================
  model:
    provider: "deepseek"          # 模型提供商
    name: "deepseek-chat"       # 模型名称
    temperature: 0.7             # 温度参数
    max_tokens: 4096             # 最大输出Token
    base_url: ""                # 自定义 API 地址

  # ==================== Agent 配置 ====================
  agent:
    max_iterations: 10          # 最大迭代次数
    enable_thinking: true       # 启用思考模式
    tool_timeout: 30           # 工具执行超时(秒)
    max_tool_calls: 10          # 最大工具调用次数

  # ==================== 记忆配置 ====================
  memory:
    enabled: true               # 启用记忆
    context_window: 10          # 上下文窗口
    ttl: 604800                 # 记忆保留时间(7天)
    storage: "redis"            # 存储后端 (memory/redis)

  # ==================== TokMem 配置 ====================
  tokmem:
    enabled: true               # 启用 TokMem
    recall_mode: "hybrid"       # 召回模式 (token/rag/hybrid)
    top_k: 5                   # 召回 Top-K
    token_weight: 0.6          # Token 权重
    rag_weight: 0.4             # RAG 权重
    embedding_dim: 4096          # Embedding 维度

  # ==================== 超时配置 ====================
  timeout:
    request: 300               # 请求超时(秒)
    llm: 60                    # LLM 调用超时(秒)
    tool: 30                   # 工具执行超时(秒)
```

---

## 四、核心接口定义

### 4.1 AgentRuntime 类

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `start` | - | `None` | 启动运行时 |
| `stop` | - | `None` | 停止运行时 |
| `process` | `request: AgentRequest` | `AgentResponse` | 处理请求 |
| `register_tool` | `name: str`, `tool: Any`, `description: str` | `None` | 注册工具 |
| `unregister_tool` | `name: str` | `None` | 注销工具 |
| `list_tools` | - | `List[str]` | 列出所有工具 |
| `get_status` | - | `AgentStatus` | 获取状态 |

### 4.2 工具接口

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute` | `**kwargs` | `Any` | 执行工具 |
| `get_description` | - | `str` | 获取描述 |
| `get_parameters` | - | `dict` | 获取参数定义 |

---

## 五、核心流程设计

### 5.1 Agent Loop 流程

```
process(request)
  │
  ├─► 1. 准备上下文 _prepare_context()
  │     ├─► 获取会话记忆
  │     ├─► 调用 TokMem 召回工具
  │     └─► 构建系统提示
  │
  ├─► 2. Agent Loop (迭代)
  │     │
  │     ├─► 2.1 Reason (思考)
  │     │     ├─► 构建推理 Prompt
  │     │     ├─► 调用 LLM
  │     │     └─► 解析响应为 Thought
  │     │
  │     ├─► 2.2 Act (行动)
  │     │     ├─► 解析 Thought 中的 action
  │     │     ├─► 从 Registry 获取工具
  │     │     ├─► 执行工具
  │     │     └─► 记录工具使用到 TokMem
  │     │
  │     ├─► 2.3 Observe (观察)
  │     │     └─► 向 EventBus 发布观察事件
  │     │
  │     └─► 2.4 循环条件
  │           ├─► 有 action → 回到 2.1
  │           └─► 无 action → 结束循环
  │
  ├─► 3. 生成最终响应
  │
  ├─► 4. 保存会话记忆
  │
  └─► 5. 返回响应
```

### 5.2 上下文准备流程

```
_prepare_context(request)
  │
  ├─► 1. 构建基础上下文
  │     ├─► user_id, session_id, channel
  │     ├─► user_input
  │     └─► timestamp
  │
  ├─► 2. 获取会话记忆
  │     └─► memory_manager.get_memory(session_id)
  │
  ├─► 3. TokMem 工具召回
  │     ├─► 调用 tool_recaller.recall()
  │     ├─► 按 recall_mode 召回
  │     └─► 构建 tokmem_recalled_tools
  │
  ├─► 4. 构建系统信息
  │     ├─► model
  │     ├─► max_iterations
  │     └─► tools_available
  │
  └─► 5. 返回完整上下文
```

### 5.3 工具执行流程

```
_act(thought, context)
  │
  ├─► 1. 解析 action
  │     ├─► tool = thought.action.tool
  │     └─► args = thought.action.args
  │
  ├─► 2. 获取工具
  │     └─► tool = tool_registry[tool_name]
  │
  ├─► 3. 发布 AGENT_ACTING 事件
  │
  ├─► 4. 执行工具 (带超时)
  │     └─► asyncio.wait_for(tool.execute(), timeout)
  │
  ├─► 5. 发布 TOOL_COMPLETED 事件
  │
  ├─► 6. 记录工具使用到 TokMem
  │     ├─► tool_token_bank.update_tokens()
  │     ├─► memory_renormalizer.renormalize()
  │     └─► save()
  │
  └─► 7. 返回结果
```

---

## 六、TokMem 集成

### 6.1 TokMem 架构

TokMem (Tool Token Memory) 是运行时模块的核心特性，提供智能工具推荐：

```
┌─────────────────────────────────────────────────────┐
│              TokMem Components                      │
│  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  ToolTokenBank  │  │  ToolRecaller          │  │
│  │  (工具Token库)  │  │  (工具召回器)          │  │
│  │  - register    │  │  - recall()          │  │
│  │  - update      │  │  - token recall      │  │
│  │  - save/load   │  │  - RAG recall        │  │
│  │               │  │  - hybrid recall     │  │
│  └─────────────────┘  └─────────────────────────┘  │
│  ┌─��───────────────────────────────────────────┐     │
│  │  MemoryRenormalizer                       │     │
│  │  (记忆重整化器)                          │     │
│  │  - renormalize()                        │     │
│  └─────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

### 6.2 召回模式

| 模式 | 说明 | 权重配置 |
|------|------|----------|
| `token` | 基于 Token 频率召回 | token_weight=1.0 |
| `rag` | 基于向量相似度召回 | rag_weight=1.0 |
| `hybrid` | 混合召回 (默认) | token_weight + rag_weight |

### 6.3 召回结果结构

```python
@dataclass
class RecallResult:
    """召回结果"""
    tool_id: str           # 工具ID
    tool_name: str        # 工具名称
    score: float         # 召回分数
    source: str          # 召回来源 (token/rag)
    description: str      # 工具描述
```

---

## 七、API 接口定义

### 7.1 管理接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/runtime/status` | GET | 获取运行时状态 |
| `/api/runtime/start` | POST | 启动运行时 |
| `/api/runtime/stop` | POST | 停止运行时 |

### 7.2 执行接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/runtime/process` | POST | 处理请求 |
| `/api/runtime/process/stream` | POST | 流式处理 |

### 7.3 工具接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/runtime/tools` | GET | 获取工具列表 |
| `/api/runtime/tools/:name` | GET | 获取工具详情 |
| `/api/runtime/tools/:name/execute` | POST | 执行工具 |

---

## 八、事件定义

### 8.1 事件类型

| 事件名 | 说明 |
|--------|------|
| `AGENT_STARTED` | Agent 已启动 |
| `AGENT_STOPPED` | Agent 已停止 |
| `AGENT_THINKING` | Agent 思考中 |
| `AGENT_ACTING` | Agent 执行工具中 |
| `AGENT_OBSERVING` | Agent 观察中 |
| `AGENT_COMPLETED` | Agent 执行完成 |
| `AGENT_ERROR` | Agent 执行错误 |
| `TOOL_INVOKED` | 工具已调用 |
| `TOOL_COMPLETED` | 工具执行完成 |
| `TOOL_FAILED` | 工具执行失败 |

### 8.2 事件数据结构

```python
@dataclass
class Event:
    """事件结构"""
    id: str                  # 事件ID
    type: EventType          # 事件类型
    source: str              # 事件来源
    data: Dict               # 事件数据
    timestamp: datetime     # 时间戳
```

---

## 九、使用示例

### 9.1 创建运行时实例

```python
from aiPlat_app.runtime import AgentRuntime, AgentConfig

# 创建配置
config = AgentConfig(
    model_provider="deepseek",
    model_name="deepseek-chat",
    temperature=0.7,
    max_iterations=10,
    memory_enabled=True,
    tokmem_enabled=True,
)

# 创建运行时
runtime = AgentRuntime(config=config)
```

### 9.2 启动和停止

```python
# 启动
await runtime.start()
print(f"Runtime status: {runtime.get_status()}")

# 停止
await runtime.stop()
print(f"Runtime status: {runtime.get_status()}")
```

### 9.3 处理请求

```python
from aiPlat_app.runtime import AgentRequest

# 创建请求
request = AgentRequest(
    user_input="请帮我检查这段代码的bug",
    user_id="user_123",
    session_id="session_001",
    channel="telegram",
)

# 处理
response = await runtime.process(request)

print(f"Status: {response.status}")
print(f"Content: {response.content}")
print(f"Tool calls: {response.tool_calls}")
```

### 9.4 注册工具

```python
class CodeAnalyzer:
    """代码分析工具"""
    
    async def execute(self, code: str, language: str = "python"):
        # 分析代码
        return {"issues": [], "score": 10}
    
    @property
    def description(self):
        return "分析代码质量问题"
    
    @property
    def parameters(self):
        return {"code": "str", "language": "str"}

# 注册工具
runtime.register_tool(
    name="code_analyzer",
    tool=CodeAnalyzer(),
    description="分析代码质量问题"
)

# 列出工具
print(runtime.list_tools())
```

### 9.5 使用 TokMem

```python
# 检查 TokMem 状态
if runtime.tool_recaller:
    # 手动召回工具
    result = await runtime.tool_recaller.recall(
        query="如何修复空指针错误",
        mode="hybrid",
        top_k=5
    )
    
    for r in result.results:
        print(f"Tool: {r.tool_name}, Score: {r.score}, Source: {r.source}")
```

---

## 十、设计原则

### 10.1 核心设计原则

1. **循环驱动**：基于 Reason → Act → Observe 循环，确保 AI 行为可控
2. **迭代控制**：通过 max_iterations 防止无限循环
3. **超时保护**：每个操作都有超时设置，防止挂起
4. **记忆持久**：会话级记忆管理，支持持久化
5. **TokMem 集成**：智能工具推荐，提高工具调用准确率

### 10.2 安全设计

1. **工具隔离**：工具在独立作用域执行
2. **超时控制**：所有 I/O 操作都有超时
3. **错误恢复**：完善的错误处理和状态恢复
4. **审计日志**：所有操作都有日志记录

### 10.3 性能设计

1. **异步处理**：所有 I/O 操作都使用异步
2. **工具缓存**：工具注册表缓存
3. **记忆分页**：大记忆分页加载
4. **TokMem 批量**：批量更新 Token Bank

---

##十一、与旧系统差异

### 11.1 架构差异

| 方面 | 旧系统 (RANGEN) | 新系统 (aiPlat-app) |
|------|----------------|-------------------|
| 模块位置 | apps/gateway/agents/ | aiPlat_app/runtime/ |
| 配置方式 | Python 配置类 | YAML 配置文件 |
| LLM 集成 | 内置调用 | 复用 aiPlat-infra |
| 事件处理 | 自定义 EventBus | 复用 events 模块 |

### 11.2 功能差异

| 方面 | 旧系统 | 新系统 |
|------|--------|--------|
| Agent Loop | 同步 | 异步 |
| TokMem | 可选 | 默认启用 |
| 多模型支持 | DeepSeek | 多提供商 |
| 工具调用 | 反射 | Registry |

---

## 十二、相关文档

- [channels 通道适配器文档](../channels/index.md)
- [events 事件总线文档](../events/index.md)
- [events 事件总线文档](../events/index.md)
- [channels 通道适配器文档](../channels/index.md)
- [management 管理平面 - Layer 3 应用层](../management/layer3_app/index.md)
- [aiPlat-infra memory 内存模块](../../aiPlat-infra/docs/memory/index.md)
- [aiPlat-infra llm LLM 模块](../../aiPlat-infra/docs/llm/index.md)