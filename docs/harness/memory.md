# 多层记忆架构设计

## 概述

本文档描述如何在 aiPlat-core 系统中实现多层记忆架构，解决 Agent 长周期运行中的"失忆"问题，实现上下文压缩、系统提醒和跨会话记忆。

## 背景

长周期 Agent 任务面临的挑战：
- **上下文膨胀**：对话变长，上下文超出窗口限制
- **指令衰减**：模型对初始 System Prompt 的关注度逐渐降低
- **记忆丢失**：跨会话信息无法保留
- **资源浪费**：无关信息占用宝贵的 Token

Harness Engineering 的解决方案：分层记忆架构 + 五级压缩策略 + 系统提醒机制。

## 目标

1. **分层管理** - Working/Episodic/Semantic 三层记忆
2. **自动压缩** - 五级阈值触发上下文压缩
3. **系统提醒** - 关键节点注入提醒防止"走神"
4. **持久化** - 跨会话记忆存储和检索
5. **Token 优化** - 减少长任务的 Token 消耗

## 现有组件

### ContextService (已存在)

位置: `core/services/context_service.py`

功能:
- 会话上下文管理 (SessionContext)
- 上下文生命周期管理
- TTL 和过期管理

### ContextLoader (已存在)

位置: `core/harness/context/loader.py`

功能:
- 按需加载上下文
- 目录摘要生成
- 上下文裁剪

## 设计方案

### 1. 三层记忆架构

```
┌─────────────────────────────────────────────┐
│              Semantic Memory                │
│         (长期记忆 - 向量存储)                 │
│    跨会话知识、用户偏好、经验总结              │
└─────────────────────────────────────────────┘
                     ↑
                     │
┌─────────────────────────────────────────────┐
│             Episodic Memory                 │
│         (会话摘要 - LLM 生成)                │
│    当前会话的完整轨迹摘要                      │
└─────────────────────────────────────────────┘
                     ↑
                     │
┌─────────────────────────────────────────────┐
│             Working Memory                  │
│         (工作记忆 - 滑动窗口)                 │
│    当前任务的最小必要信息                       │
└─────────────────────────────────────────────┘
```

### 2. 各层详细设计

#### Working Memory（工作记忆）

当前任务所需的最小信息：

| 属性 | 值 |
|------|-----|
| 存储位置 | 内存（当前会话） |
| 生命周期 | 单个任务 |
| 容量 | Token 上限的 30% |
| 管理方式 | 滑动窗口（保留最近 N 轮） |

```python
class WorkingMemory:
    """工作记忆 - 当前任务最小信息"""
    
    def __init__(self, max_tokens: int = 30000):
        self._max_tokens = max_tokens
        self._messages = deque(maxlen=20)  # 最近 20 轮
    
    def add(self, message: Message):
        """添加消息，自动裁剪"""
        self._messages.append(message)
        self._ensure_within_limit()
    
    def get_context(self) -> List[Message]:
        """获取当前上下文"""
        return list(self._messages)
```

#### Episodic Memory（情景记忆）

当前会话的完整轨迹摘要：

| 属性 | 值 |
|------|-----|
| 存储位置 | 内存 + 持久化 |
| 生命周期 | 当前会话 |
| 更新频率 | 每 5 轮对话 |
| 生成方式 | LLM 摘要 |

```python
class EpisodicMemory:
    """情景记忆 - 会话轨迹摘要"""
    
    def __init__(self, llm: LLM):
        self._llm = llm
        self._summary = ""
        self._message_count = 0
        self._update_interval = 5
    
    async def should_update(self) -> bool:
        """判断是否需要更新摘要"""
        return self._message_count >= self._update_interval
    
    async def update_summary(self, messages: List[Message]):
        """生成新的会话摘要"""
        prompt = f"请用 100 字概括以下对话的要点：\n{messages}"
        self._summary = await self._llm.generate(prompt)
        self._message_count = 0
```

#### Semantic Memory（语义记忆）

跨会话的长期知识存储：

| 属性 | 值 |
|------|-----|
| 存储位置 | 向量数据库 |
| 生命周期 | 永久（可配置 TTL） |
| 检索方式 | 向量相似度 |
| 用途 | 用户偏好、经验总结 |

```python
class SemanticMemory:
    """语义记忆 - 长期知识"""
    
    def __init__(self, vector_store: VectorStore):
        self._store = vector_store
    
    async def store(self, key: str, value: str, metadata: Dict = None):
        """存储知识"""
        embedding = await self._embed(value)
        await self._store.add(
            id=key,
            vector=embedding,
            text=value,
            metadata=metadata or {}
        )
    
    async def retrieve(self, query: str, top_k: int = 3) -> List[MemoryItem]:
        """检索相关知识"""
        query_embedding = await self._embed(query)
        return await self._store.search(query_embedding, top_k)
```

### 3. 五级压缩策略

基于 OpenDev 的分级压缩：

| 级别 | 阈值 | 策略 | Token 节省 |
|------|------|------|------------|
| **正常** | < 70% | 无操作 | - |
| **警告** | 70-80% | 监控频率提升 | - |
| **替换** | 80-85% | 旧工具输出→摘要引用 | ~20% |
| **裁剪** | 85-90% | 仅保留最近 N 轮完整输出 | ~40% |
| **激进** | 90-99% | 仅保留核心信息 | ~60% |
| **紧急** | ≥ 99% | LLM 完整摘要 | ~80% |

```python
class ContextCompression:
    """上下文压缩策略"""
    
    def __init__(self):
        self._thresholds = [
            (0.70, self._handle_warning),
            (0.80, self._handle_replace),
            (0.85, self._handle_prune),
            (0.90, self._handle_aggressive),
            (0.99, self._handle_emergency)
        ]
    
    async def compress(self, context: Context) -> Context:
        """执行压缩"""
        usage = context.token_usage / context.token_limit
        
        for threshold, handler in self._thresholds:
            if usage >= threshold:
                context = await handler(context)
        
        return context
    
    async def _handle_replace(self, context: Context) -> Context:
        """旧工具输出替换为摘要引用"""
        # 将旧的工具输出替换为 "见上文工具输出 #N"
        pass
    
    async def _handle_prune(self, context: Context) -> Context:
        """只保留最近 5 轮完整输出"""
        # 裁剪早期消息，只保留最近 5 轮
        pass
    
    async def _handle_aggressive(self, context: Context) -> Context:
        """激进压缩，只保留核心"""
        # 只保留系统提示 + 最近 2 轮 + 情景摘要
        pass
    
    async def _handle_emergency(self, context: Context) -> Context:
        """紧急压缩，LLM 完整摘要"""
        # 调用 LLM 生成完整摘要替换整个上下文
        pass
```

### 4. 系统提醒机制（System Reminders）

解决"指令衰减"问题：

| 事件 | 条件 | 提醒内容 |
|------|------|----------|
| 未完成 Todo | 调用 task_complete 时有未完成项 | "还有 XX 个任务未完成" |
| 探索螺旋 | 连续 5 次只读操作 | "已连续探索 5 个文件，该开始行动了" |
| 工具失败 | 工具调用失败 | "请检查参数或尝试其他工具" |
| 上下文过载 | Token 使用 > 90% | "上下文即将耗尽，建议总结当前进度" |

```python
class SystemReminder:
    """系统提醒机制"""
    
    def __init__(self):
        self._rules = [
            ReminderRule(
                trigger=self._check_unfinished_todos,
                message_template="还有 {count} 个任务未完成: {items}"
            ),
            ReminderRule(
                trigger=self._check_exploration_spiral,
                message_template="已连续探索 {count} 个文件，该开始行动了"
            ),
            ReminderRule(
                trigger=self._check_tool_failure,
                message_template="工具调用失败: {error}"
            )
        ]
    
    async def check_and_inject(self, state: AgentState) -> Optional[str]:
        """检查是否需要注入提醒"""
        for rule in self._rules:
            if await rule.trigger(state):
                return rule.generate_message(state)
        return None
```

### 5. 记忆整合流程

```python
class MemoryManager:
    """记忆管理器 - 整合三层记忆"""
    
    def __init__(
        self,
        working: WorkingMemory,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        compression: ContextCompression
    ):
        self._working = working
        self._episodic = episodic
        self._semantic = semantic
        self._compression = compression
    
    async def build_context(
        self,
        current_query: str,
        system_prompt: str
    ) -> List[Message]:
        """构建完整上下文"""
        # 1. 获取语义记忆（长期知识）
        relevant_memories = await self._semantic.retrieve(current_query)
        
        # 2. 获取情景摘要（当前会话）
        episodic_summary = await self._episodic.get_summary()
        
        # 3. 获取工作记忆（最近消息）
        working_context = self._working.get_context()
        
        # 4. 检查压缩阈值
        context = system_prompt + relevant_memories + episodic_summary + working_context
        if context.token_usage > context.token_limit * 0.9:
            context = await self._compression.compress(context)
        
        return context
    
    async def save_interaction(
        self,
        user_message: Message,
        agent_message: Message,
        tool_calls: List[ToolCall]
    ):
        """保存交互到记忆"""
        # 保存到工作记忆
        self._working.add(user_message)
        self._working.add(agent_message)
        
        # 更新情景记忆
        await self._episodic.add_interaction(user_message, agent_message, tool_calls)
        
        # 检查是否需要提取到语义记忆
        if should_capture_to_semantic(agent_message):
            await self._semantic.store(
                key=f"pattern:{uuid}",
                value=extract_pattern(agent_message)
            )
```

## 模块结构

```
core/harness/memory/
├── __init__.py
├── working.py          # 工作记忆
├── episodic.py         # 情景记忆
├── semantic.py         # 语义记忆
├── compression.py      # 压缩策略
├── reminders.py        # 系统提醒
└── manager.py         # 记忆管理器
```

## 核心组件

### MemoryManager

```python
class MemoryManager:
    """统一记忆管理器"""
    
    def __init__(self, config: MemoryConfig):
        self._working = WorkingMemory(config.working_tokens)
        self._episodic = EpisodicMemory(config.llm, config.update_interval)
        self._semantic = SemanticMemory(config.vector_store)
        self._compression = ContextCompression()
        self._reminders = SystemReminder()
    
    async def build_context(self, query: str) -> Context:
        """构建完整上下文"""
        pass
    
    async def save(self, interaction: Interaction):
        """保存交互记录"""
        pass
    
    async def check_reminders(self, state: AgentState) -> Optional[str]:
        """检查并注入系统提醒"""
        pass
```

### ContextCompression

```python
class ContextCompression:
    """上下文压缩"""
    
    # 五级压缩策略
    STRATEGIES = {
        "normal": (0, 0.70),
        "warning": (0.70, 0.80),
        "replace": (0.80, 0.85),
        "prune": (0.85, 0.90),
        "aggressive": (0.90, 0.99),
        "emergency": (0.99, 1.0)
    }
```

## 与现有系统集成

### 与 ContextService 集成

```python
# ContextService 中集成多层记忆
class ContextService:
    def __init__(self):
        self._memory = MemoryManager(config)
    
    async def get_context(self, session_id: str):
        session = await self._get_session(session_id)
        return await self._memory.build_context(
            current_query=session.current_query,
            system_prompt=session.system_prompt
        )
```

### 与 ToolExecutor 集成

工具执行后保存到记忆：

```python
class ToolExecutor:
    async def execute(self, tool: Tool, params: Dict):
        result = await tool.execute(params)
        
        # 保存到记忆
        await self._memory.save_interaction(
            tool=tool.name,
            params=params,
            result=result,
            success=result.success
        )
        
        return result
```

### 与 Quality Gate 集成

压缩前运行质量检查：

```python
# ContextCompression 中集成
async def compress(self, context: Context):
    if context.token_usage > context.token_limit * 0.9:
        # 运行质量门禁
        result = await quality_gate.check(context)
        if not result.passed:
            logger.warning(f"上下文质量不通过: {result.message}")
    
    return await self._do_compress(context)
```

## 性能指标

| 指标 | 目标值 |
|------|--------|
| 上下文峰值降低 | > 50% |
| Token 消耗降低 | > 30% |
| 提醒准确率 | > 80% |
| 语义检索准确率 | > 85% |

## 使用方式

### 1. 配置记忆系统

```python
from core.harness.memory import MemoryManager, MemoryConfig

config = MemoryConfig(
    working_tokens=30000,
    episodic_update_interval=5,
    vector_store=ChromaVectorStore(),
    compression_thresholds=[0.70, 0.80, 0.85, 0.90, 0.99]
)

memory = MemoryManager(config)
```

### 2. 构建上下文

```python
context = await memory.build_context(
    current_query="帮我重构这个函数",
    system_prompt="你是一个专业程序员..."
)
```

### 3. 手动触发压缩

```python
# 强制压缩
compressed = await memory.compression.compress(context)
```

### 4. 查看记忆状态

```python
status = await memory.get_status()
# {
#   "working": {"tokens": 15000, "messages": 12},
#   "episodic": {"summary": "...", "updated_at": "..."},
#   "semantic": {"items": 150}
# }
```

## 待实现

- [ ] core/harness/memory/ 模块实现
- [ ] WorkingMemory 实现
- [ ] EpisodicMemory 实现（LLM 摘要生成）
- [ ] SemanticMemory 实现（向量存储）
- [ ] ContextCompression 实现（五级策略）
- [ ] SystemReminder 实现
- [ ] 与 ContextService 集成
- [ ] 与 ToolExecutor 集成