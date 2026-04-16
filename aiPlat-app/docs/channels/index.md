# 通道适配器模块

> 通道适配器模块是 AI Platform 应用层的多渠道接入层，提供统一的渠道抽象，支持 Telegram、Slack、WebChat、WhatsApp 等多种消息渠道的接入与管理。

---

## 一、模块定位

### 1.1 核心职责

通道适配器模块在整个 AI Platform 架构中承担以下核心职责：

| 职责 | 说明 |
|------|------|
| **渠道接入** | 提供统一的渠道适配接口 |
| **消息收发** | 处理消息的接收和发送 |
| **用户识别** | 解析和映射渠道用户 |
| **消息转换** | 渠道消息格式转换 |
| **交互支持** | 支持按钮、轮播等交互 |

### 1.2 与相邻模块的关系

```
┌─────────────────────────────────────────────────────────────┐
│                 External Channels                            │
│  ┌───────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Telegram │  │ Slack  │  │ WebChat │  │  ...   │  │
│  └─────┬─────┘  └────┬────┘  └───┬──────┘  └────┬────┘  │
└────────┼──────────────┼─────────────┼──────────────┼────────┘
         │             │             │              │
         ▼             ▼             ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Channel Adapters                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           ChannelAdapter (Base)                   │  │
│  │  ┌───────────────┐  ┌────────────────────────┐     │  │
│  │  │ Polling     │  │  Webhook             │     │  │
│  │  │ (轮询模式)  │  │  (Webhook模式)        │     │  │
│  │  └───────────────┘  └────────────────────────┘     │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Gateway                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Router    │  │  Auth       │  │  Session Manager   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心概念定义

### 2.1 MessageType 枚举

```python
class MessageType(Enum):
    """消息类型"""
    TEXT = "text"           # 文本
    IMAGE = "image"        # 图片
    VIDEO = "video"        # 视频
    AUDIO = "audio"        # 音频
    FILE = "file"          # 文件
    LOCATION = "location"  # 位置
    BUTTON = "button"       # 按钮
    INTERACTIVE = "interactive"  # 交互
```

### 2.2 User 结构

```python
@dataclass
class User:
    """用户信息"""
    id: str                              # 用户ID
    name: str = ""                       # 显示名称
    username: str = ""                   # 用户名
    first_name: str = ""                 # 名字
    last_name: str = ""                  # 姓氏
    language: str = "en"                # 语言
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据
```

### 2.3 Message 结构

```python
@dataclass
class Message:
    """消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 消息ID
    channel: str = ""                   # 渠道标识
    type: MessageType = MessageType.TEXT  # 消息类型
    content: str = ""                  # 消息内容
    user: User = field(default_factory=User)  # 用户信息
    timestamp: datetime = field(default_factory=datetime.now)  # 时间戳

    # 可选字段
    reply_to: str = ""                 # 回复的消息ID
    attachments: list[str] = field(default_factory=list)  # 附件
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> dict:
        return {...}
```

### 2.4 ChannelAdapter 抽象基类

```python
class ChannelAdapter(ABC):
    """消息渠道适配器基类"""
    
    def __init__(self, channel_id: str, config: Optional[dict] = None):
        self.channel_id = channel_id
        self.config = config or {}
        self.gateway = None
        self._running = False
```

---

## 三、配置结构

### 3.1 通道配置

```yaml
# aiPlat-app/channels/config.yaml

channels:
  # ==================== 通用配置 ====================
  common:
    allowed_users: []            # 允许的用户ID列表（空=全部）
    blocked_users: []            # 禁止的用户ID列表
    max_message_length: 4000     # 最大消息长度
    typing_indicator: true       # 显示输入状态
    
  # ==================== Telegram 配置 ====================
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    webhook_url: ""             # webhook 地址
    secret_token: "${TELEGRAM_SECRET}"
    
  # ==================== Slack 配置 ====================
  slack:
    enabled: false
    bot_token: "${SLACK_BOT_TOKEN}"
    app_token: "${SLACK_APP_TOKEN}"
    signing_secret: "${SLACK_SIGNING_SECRET}"
    
  # ==================== WebChat 配置 ====================
  webchat:
    enabled: false
    host: "0.0.0.0"
    port: 8080
    path: "/webhook"
```

---

## 四、核心接口定义

### 4.1 ChannelAdapter 基类接口

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `connect` | - | `bool` | 连接渠道 |
| `disconnect` | - | `None` | 断开连接 |
| `send` | `chat_id, text, reply_to` | `bool` | 发送消息 |
| `send_interactive` | `chat_id, text, buttons` | `bool` | 发送交互消息 |
| `send_typing` | `chat_id, typing` | `None` | 发送输入状态 |
| `start_listening` | - | `None` | 开���监听 |
| `stop_listening` | - | `None` | 停止监听 |
| `get_stats` | - | `dict` | 获取统计 |

### 4.2 抽象方法

| 方法 | 说明 |
|------|------|
| `_listen` | 监听循环 |
| `_parse_message` | 解析原始消息 |

### 4.3 PollingChannelAdapter 接口

```python
class PollingChannelAdapter(ChannelAdapter):
    """基于轮询的渠道适配器"""
    
    async def _fetch_messages(self) -> list[dict]:
        """获取新消息（子类实现）"""
        pass
```

### 4.4 WebhookChannelAdapter 接口

```python
class WebhookChannelAdapter(ChannelAdapter):
    """基于 Webhook 的渠道适配器"""
    
    async def setup_webhook(self, webhook_url: str) -> bool:
        """设置 Webhook"""
        pass
```

---

## 五、核心流程设计

### 5.1 消息接收流程

```
_listen()  [Polling 模式]
  │
  ├─► 1. 轮询获取消息
  │     └─► _fetch_messages()
  │
  ├─► 2. 遍历消息
  │     └─► 对每条消息调用 _handle_message()
  │
  └─► 3. 等待间隔
        └─► asyncio.sleep(poll_interval)
```

### 5.2 消息处理流程

```
_handle_message(raw_message)
  │
  ├─► 1. 解析消息
  │     └─► _parse_message(raw_message)
  │
  ├─► 2. 有效性检查
  │     └─► 消息为空则跳过
  │
  ├─► 3. 更新统计
  │     └─► messages_received += 1
  │
  ├─► 4. 转发 Gateway
  │     └─► gateway.handle_message(message)
  │
  └─► 5. 异常处理
        └─► 错误计入 stats.errors
```

### 5.3 消息发送流程

```
send(chat_id, text, reply_to)
  │
  ├─► 1. 验证渠道连接
  │
  ├─► 2. 调用渠道API发送
  │
  ├─► 3. 更新统计
  │     └─► messages_sent += 1
  │
  └─► 4. 返回结果
```

---

## 六、预置通道适配器

### 6.1 Telegram 适配器

```python
class TelegramAdapter(PollingChannelAdapter):
    """Telegram 适配器"""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__("telegram", config)
        self.bot = None
        
    async def connect(self) -> bool:
        # 初始化 Telegram Bot
        pass
        
    async def send(self, chat_id, text, reply_to=None):
        # 调用 Telegram API
        pass
```

### 6.2 Slack 适配器

```python
class SlackAdapter(WebhookChannelAdapter):
    """Slack 适配器"""
    
    async def setup_webhook(self, webhook_url) -> bool:
        # 注册 Slack Webhook
        pass
```

### 6.3 WebChat 适配器

```python
class WebChatAdapter(WebhookChannelAdapter):
    """WebChat 适配器"""
    
    async def connect(self):
        # 启动 Web 服务器
        pass
```

---

## 七、统计信息

### 7.1 通道统计

```python
def get_stats(self) -> dict:
    return {
        "channel_id": str,           # 通道ID
        "running": bool,            # 是否运行中
        "messages_sent": int,       # 发送消息数
        "messages_received": int,   # 接收消息数
        "errors": int              # 错误数
    }
```

---

## 八、使用示例

### 8.1 创建 Telegram 通道

```python
from aiPlat_app.channels import TelegramAdapter

# 创建通道
telegram = TelegramAdapter(config={
    "bot_token": "your-bot-token",
    "allowed_users": ["user123"]
})

# 设置 Gateway
telegram.set_gateway(gateway)
```

### 8.2 连接和断开

```python
# 连接
await telegram.connect()
print(f"Connected: {telegram.channel_id}")

# 开始监听
await telegram.start_listening()

# ���止���听
await telegram.stop_listening()

# 断开
await telegram.disconnect()
```

### 8.3 发送消息

```python
# 发送文本消息
await telegram.send(
    chat_id="123456789",
    text="Hello, World!"
)

# 发送带按钮的消息
await telegram.send_interactive(
    chat_id="123456789",
    text="请选择选项",
    buttons=[
        {"id": "btn_1", "text": "选项 1"},
        {"id": "btn_2", "text": "选项 2"}
    ]
)

# 发送 typing 状态
await telegram.send_typing(chat_id="123456789", typing=True)
```

### 8.4 获取统计

```python
stats = telegram.get_stats()
print(f"Messages sent: {stats['messages_sent']}")
print(f"Messages received: {stats['messages_received']}")
print(f"Errors: {stats['errors']}")
```

---

## 九、安全设计

### 9.1 用户过滤

1. **允许列表**：只处理允许列表中的用户消息
2. **禁止列表**：过滤禁止列表中的用户
3. **默认拒绝**：可配置默认拒绝未知用户

### 9.2 消息验证

1. **长度限制**：限制消息最大长度
2. **格式验证**：验证消息格式
3. **速率限制**：防止消息洪水

### 9.3 Webhook 安全

1. **Secret Token**：验证 Webhook 请求
2. **IP 白名单**：限制 Webhook 来源 IP

---

## 十、与旧系统差异

### 10.1 架构差异

| 方面 | 旧系统 (RANGEN) | 新系统 (aiPlat-app) |
|------|----------------|-------------------|
| 模块位置 | apps/gateway/channels/ | aiPlat_app/channels/ |
| 基类设计 | 自定义 | 抽象基类 |
| 轮询模式 | 内置 | PollingChannelAdapter |

### 10.2 功能差异

| 方面 | 旧系统 | 新系统 |
|------|--------|--------|
| 交互消息 | 部分支持 | 完整支持 |
| Typing 状态 | 无 | 支持 |
| 统计 | 基础 | 完整 |

---

## 十一、相关文档

- [runtime 运行时文档](../runtime/index.md)
- [events 事件总线文档](../events/index.md)
- [runtime 运行时文档](../runtime/index.md)
- [events 事件总线文档](../events/index.md)
- [management 管理平面 - Layer 3 应用层](../../../aiPlat-management/docs/app/index.md)
