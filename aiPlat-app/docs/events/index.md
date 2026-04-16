# 事件总线模块

> 事件总线模块是 AI Platform 应用层的消息通信中枢，提供发布-订阅模式的事件驱动机制，用于模块间的解耦通信。

---

## 一、模块定位

### 1.1 核心职责

事件总线模块在整个 AI Platform 架构中承担以下核心职责：

| 职责 | 说明 |
|------|------|
| **事件发布** | 支持异步事件发布 |
| **事件订阅** | 支持多处理器订阅 |
| **队列管理** | 事件队列缓冲与背压控制 |
| **统计监控** | 事件处理统计 |

### 1.2 与相邻模块的关系

```
┌─────────────────────────────────────────────────────────────┐
│                 Publisher Modules                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │  Gateway   │  │  Runtime   │  │  Channels          │   │
│  └──────┬──────┘  └──────┬──────┘  └─────────┬─────────┘   │
└────────┼──────────────────┼────────────────────┼─────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      EventBus                             │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Event Queue                            │ │
│  │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐            │ │
│  │  │Event1 │ │Event2 │ │Event3 │ │ ...  │            │ │
│  │  └───────┘ └───────┘ └───────┘ └───────┘            │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           Event Processor                            │ │
│  │           (异步处理循环)                              │ │
│  └─────────────────────────────────────────────────────┘ │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                Subscriber Modules                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │  Logger   │  │  Metrics   │  │  Custom Handlers   │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心概念定义

### 2.1 EventType 枚举

```python
class EventType(Enum):
    """事件类型"""
    
    # 生命周期事件
    GATEWAY_STARTED = "gateway_started"
    GATEWAY_STOPPED = "gateway_stopped"
    
    # 渠道事件
    CHANNEL_REGISTERED = "channel_registered"
    CHANNEL_UNREGISTERED = "channel_unregistered"
    CHANNEL_MESSAGE_SENT = "channel_message_sent"
    CHANNEL_MESSAGE_RECEIVED = "channel_message_received"
    
    # 消息事件
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PROCESSED = "message_processed"
    MESSAGE_FAILED = "message_failed"
    
    # Agent 事件
    AGENT_STARTED = "agent_started"
    AGENT_THINKING = "agent_thinking"
    AGENT_ACTING = "agent_acting"
    AGENT_OBSERVING = "agent_observing"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"
    
    # 工具事件
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    
    # 记忆事件
    MEMORY_LOADED = "memory_loaded"
    MEMORY_SAVED = "memory_saved"
    MEMORY_COMPACTED = "memory_compacted"
    
    # 系统事件
    HEARTBEAT = "heartbeat"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    KILL_SWITCH_DEACTIVATED = "kill_switch_deactivated"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
```

### 2.2 Event 结构

```python
@dataclass
class Event:
    """事件结构"""
    type: EventType              # 事件类型
    data: dict[str, Any] = field(default_factory=dict)  # 事件数据
    timestamp: datetime = field(default_factory=datetime.now)  # 时间戳
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 事件ID
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }
```

### 2.3 EventHandler 类型

```python
EventHandler = Callable[[Event], Awaitable[None]]
```

---

## 三、配置结构

### 3.1 事件总线配置

```yaml
# aiPlat-app/events/config.yaml

events:
  # ==================== 队列配置 ====================
  queue:
    max_size: 1000              # 队列最大大小
    overflow_strategy: "drop"   # 溢出策略 (drop/reject)
    
  # ==================== 处理配置 ====================
  processor:
    workers: 4                # 工作线程数
    timeout: 30               # 处理超时(秒)
    retry_count: 3            # 重试次数
    
  # ==================== 统计配置 ====================
  stats:
    enabled: true             # 启用统计
    interval: 60               # 统计间隔(秒)
```

---

## 四、核心接口定义

### 4.1 EventBus 类

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `start` | - | `None` | 启动事件总线 |
| `stop` | - | `None` | 停止事件总线 |
| `subscribe` | `event_type: EventType`, `handler: EventHandler` | `None` | 订阅事件 |
| `unsubscribe` | `event_type: EventType`, `handler: EventHandler` | `None` | 取消订阅 |
| `emit` | `event: Event` | `None` | 发布事件 (异步) |
| `emit_sync` | `event: Event` | `None` | 同步发布 |
| `get_stats` | - | `dict` | 获取统计信息 |

### 4.2 统计信息

```python
def get_stats(self) -> dict:
    return {
        "events_published": int,    # 已发布事件数
        "events_processed": int,    # 已处理事件数
        "events_dropped": int,       # 丢弃事件数
        "queue_size": int,          # 当前队列大小
        "subscribed_types": list,   # 订阅的事件类型
        "total_handlers": int,     # 总处理器数
    }
```

---

## 五、核心流程设计

### 5.1 事件发布流程

```
emit(event)
  │
  ├─► 1. 增加发布计数
  │
  ├─► 2. 尝试放入队列
  │     ├─► 队列未满 → 放入成功
  │     └─► 队列已满 → 丢弃事件，增加丢弃计数
  │
  └─► 3. 返回
```

### 5.2 事件处理流程

```
_process_events()  [异步循环]
  │
  ├─► 1. 从队列获取事件
  │     └─► 超时则继续等待
  │
  ├─► 2. 调用 _handle_event()
  │     ├─► 获取事件类型的处理器列表
  │     └─► 并发执行所有处理器
  │
  └─► 3. 更新统计信息
```

### 5.3 同步发布流程

```
emit_sync(event)
  │
  ├─► 1. 直接调用 _handle_event()
  │
  └─► 2. 等待所有处理器完成
```

---

## 六、事件分类

### 6.1 生命周期事件

| 事件名 | 数据字段 | 说明 |
|--------|----------|------|
| `GATEWAY_STARTED` | `config` | 网关已启动 |
| `GATEWAY_STOPPED` | - | 网关已停止 |

### 6.2 消息事件

| 事件名 | 数据字段 | 说明 |
|--------|----------|------|
| `MESSAGE_RECEIVED` | `message_id, channel, user_id` | 收到消息 |
| `MESSAGE_PROCESSED` | `message_id, response` | 消息已处理 |
| `MESSAGE_FAILED` | `message_id, error` | 消息处理失败 |

### 6.3 Agent 事件

| 事件名 | 数据字段 | 说明 |
|--------|----------|------|
| `AGENT_STARTED` | `config` | Agent 已启动 |
| `AGENT_THINKING` | `session_id` | Agent 思考中 |
| `AGENT_ACTING` | `tool, args, session_id` | Agent 执行工具中 |
| `AGENT_OBSERVING` | `result_type, session_id` | Agent 观察中 |
| `AGENT_COMPLETED` | `response_length, iterations` | Agent 执行完成 |
| `AGENT_ERROR` | `error, session_id` | Agent 执行错误 |

### 6.4 工具事件

| 事件名 | 数据字段 | 说明 |
|--------|----------|------|
| `TOOL_INVOKED` | `tool, args, session_id` | 工具已调用 |
| `TOOL_COMPLETED` | `tool, result_length` | 工具执行完成 |
| `TOOL_FAILED` | `tool, error` | 工具执行失败 |

### 6.5 系统事件

| 事件名 | 数据字段 | 说明 |
|--------|----------|------|
| `HEARTBEAT` | `timestamp` | 心跳 |
| `KILL_SWITCH_ACTIVATED` | `reason` | Kill Switch 已激活 |
| `RATE_LIMIT_EXCEEDED` | `user_id, limit` | 速率超限 |

---

## 七、使用示例

### 7.1 创建事件总线

```python
# 伪代码：当前仓库未提供 app 层 Python 的 EventBus 实现。
# 如果需要落地实现，请以平台对外契约（platform API）与 management 的可观测性链路为准。
from typing import Any, Dict

# 创建事件总线
event_bus = ...  # EventBus(max_queue_size=1000)
```

### 7.2 启动和停止

```python
# 启动
await event_bus.start()
print(f"EventBus started")

# 停止
await event_bus.stop()
stats = event_bus.get_stats()
print(f"Stats: {stats}")
```

### 7.3 订阅事件

```python
async def handle_agent_completed(event: Event):
    """处理 Agent 完成事件"""
    data = event.data
    print(f"Agent completed: {data.get('iterations')} iterations")
    print(f"Response length: {data.get('response_length')}")

# 订阅事件
event_bus.subscribe(EventType.AGENT_COMPLETED, handle_agent_completed)
```

### 7.4 发布事件

```python
# 发布事件
event = Event(
    type=EventType.MESSAGE_RECEIVED,
    data={"message_id": "msg_001", "channel": "telegram"}
)
await event_bus.emit(event)

# 同步发布
await event_bus.emit_sync(event)
```

### 7.5 取消订阅

```python
# 取消订阅
event_bus.unsubscribe(EventType.AGENT_COMPLETED, handle_agent_completed)
```

### 7.6 多处理器示例

```python
async def logging_handler(event: Event):
    """日志处理器"""
    logger.info(f"Event: {event.type.value}")

async def metrics_handler(event: Event):
    """指标处理器"""
    metrics.increment(f"event.{event.type.value}")

async def custom_handler(event: Event):
    """自定义处理器"""
    # 自定义逻辑
    pass

# 订阅多个处理器
event_bus.subscribe(EventType.MESSAGE_RECEIVED, logging_handler)
event_bus.subscribe(EventType.MESSAGE_RECEIVED, metrics_handler)
event_bus.subscribe(EventType.MESSAGE_RECEIVED, custom_handler)
```

---

## 八、设计原则

### 8.1 核心设计原则

1. **异步处理**：事件处理采用异步队列，避免阻塞
2. **背压控制**：队列满时丢弃事件，防止内存溢出
3. **并发处理**：同一事件的多个处理器并发执行
4. **统计监控**：提供完整的事件处理统计
5. **超时保护**：处理器执行带超时

### 8.2 安全设计

1. **异常隔离**：处理器异常不影响其他处理器
2. **队列背压**：队列满时丢弃事件，防止OOM
3. **优雅停止**：停止时等待队列处理完成

### 8.3 性能设计

1. **异步队列**：使用 asyncio.Queue
2. **并发执行**：多个处理器 asyncio.gather
3. **无锁设计**：不需要额外同步

---

## 九、与旧系统差异

### 9.1 架构差异

| 方面 | 旧系统 (RANGEN) | 新系统 (aiPlat-app) |
|------|----------------|-------------------|
| 模块位置 | apps/gateway/events/ | aiPlat_app/events/ |
| 配置方式 | Python 配置类 | YAML 配置文件 |
| 队列实现 | asyncio.Queue | asyncio.Queue |
| 统计 | 基础统计 | 完整统计 |

### 9.2 功能差异

| 方面 | 旧系统 | 新系统 |
|------|--------|--------|
| 队列溢出 | 丢弃 | 可配置策略 |
| 处理器超时 | 无 | 支持 |
| retry | 无 | 支持 |

---

## 十、相关文档

- [runtime 运行时文档](../runtime/index.md)
- [channels 通道适配器文档](../channels/index.md)
- [runtime 运行时文档](../runtime/index.md)
- [channels 通道适配器文档](../channels/index.md)
- [management 管理平面 - Layer 3 应用层](../../../aiPlat-management/docs/app/index.md)
- [aiPlat-infra observability 可观测性模块](../../../aiPlat-infra/docs/observability/index.md)
