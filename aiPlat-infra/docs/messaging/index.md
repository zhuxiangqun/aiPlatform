# Messaging 模块文档（设计真值：以代码事实为准）

> 说明：消息队列抽象的 As-Is 能力以 `infra/messaging/*` 代码与测试为准；文档中的多中间件支持（Kafka/RabbitMQ/Redis）若未闭环需标注为 To-Be。

> 消息队列抽象 - 基础设施层

---

## 模块定位

**职责**：提供消息队列的统一抽象，支持多种消息中间件（Kafka、RabbitMQ、Redis）。

**依赖方向**：
```
messaging 模块 → 被 core/platform/app 调用（通过 infra 工厂接口）
messaging 模块 → 不依赖任何内部模块
```

---

## 能力概述

### 支持的消息中间件

| 中间件 | 说明 |
|--------|------|
| **Kafka** | 分布式消息队列，高吞吐量 |
| **RabbitMQ** | 传统消息队列，可靠性高 |
| **Redis** | 轻量级消息队列，适合小规模 |

### 核心能力

| 能力 | 说明 |
|------|------|
| 发布消息 | 发送消息到指定主题/队列 |
| 订阅消息 | 订阅主题/队列，接收消息 |
| 消费确认 | ACK/NACK 消息确认机制 |
| 死信队列 | 失败消息转入死信队列 |
| 延迟消息 | 支持延迟投递 |

---

## 接口定义

### MessageClient 接口

**位置**：`infra/messaging/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `publish` | `topic: str`, `message: bytes`, `**kwargs` | `None` | 发布消息 |
| `subscribe` | `topic: str`, `handler: Callable` | `None` | 订阅主题 |
| `unsubscribe` | `topic: str` | `None` | 取消订阅 |
| `ack` | `message_id: str` | `None` | 确认消息 |
| `nack` | `message_id: str` | `None` | 拒绝消息 |
| `close` | - | `None` | 关闭连接 |

### 数据模型

| 模型 | 字段 | 说明 |

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/messaging/*`
|------|------|------|
| `Message` | `id`, `topic`, `body`, `headers`, `timestamp` | 消息结构 |
| `Topic` | `name`, `partitions`, `retention` | 主题定义 |
| `ConsumerConfig` | `group_id`, `auto_commit`, `prefetch` | 消费者配置 |

---

## 工厂函数

### Messaging 工厂

**位置**：`infra/messaging/factory.py`

**函数签名**：
```python
create_messaging_client(config: MessagingConfig) -> MessageClient
```

**配置结构**：
```python
@dataclass
class MessagingConfig:
    backend: str           # "kafka" | "rabbitmq" | "redis"
    hosts: List[str]       # 服务器地址列表
    topic_prefix: str      # 主题前缀
    client_id: str        # 客户端ID
    options: Dict[str, Any]  # 后端特定选项
```

---

## 使用示例

### 创建客户端

```python
from aiPlat_infra.messaging import create_messaging_client
from aiPlat_infra.config import MessagingConfig

config = MessagingConfig(
    backend="kafka",
    hosts=["localhost:9092"],
    topic_prefix="aiplat"
)

client = create_messaging_client(config)
```

### 发布消息

```python
# 发布消息
await client.publish(
    topic="events.user.created",
    message=b'{"user_id": "123", "name": "test"}',
    headers={"source": "api"}
)
```

### 订阅消息

```python
# 订阅主题
async def handle_message(message: Message):
    print(f"Received: {message.body}")
    await client.ack(message.id)

await client.subscribe(
    topic="events.user.created",
    handler=handle_message
)
```

---

## Kafka 实现

**位置**：`infra/messaging/kafka.py`

**配置**：
```yaml
messaging:
  backend: kafka
  hosts:
    - localhost:9092
  topic_prefix: "aiplat"
  options:
    consumer_group: "aiplat-consumer"
    auto_offset_reset: "latest"
    enable_auto_commit: true
```

**特性**：
- 高吞吐量
- 分区支持
- 消息持久化
- 消费者组

---

## RabbitMQ 实现

**位置**：`infra/messaging/rabbitmq.py`

**配置**：
```yaml
messaging:
  backend: rabbitmq
  hosts:
    - localhost:5672
  topic_prefix: "aiplat"
  options:
    username: "guest"
    password: "guest"
    vhost: "/"
    exchange_type: "topic"
```

**特性**：
- 可靠性高
- 路由灵活
- 死信队列
- 延迟消息

---

## Redis 实现

**位置**：`infra/messaging/redis.py`

**配置**：
```yaml
messaging:
  backend: redis
  hosts:
    - localhost:6379
  topic_prefix: "aiplat"
  options:
    db: 0
    password: null
  pool_size: 10
```

**特性**：
- 轻量级
- 低延迟
- 简单易用
- 适合小规模

---

## 设计原则

1. **统一接口**：抽象不同消息中间件的差异
2. **配置驱动**：通过配置切换不同后端
3. **异步优先**：默认异步 API
4. **错误处理**：内置重试和死信队列

---

## 相关文档

- [config 模块文档](../config/index.md) - 配置管理
- [observability 模块文档](../observability/index.md) - 可观测性
- [di 模块文档](../di/index.md) - 依赖注入
