# LLM 客户端模块

> 提供对多种 LLM 提供商的统一封装，支持延迟初始化、限流、重试、流式输出等特性

---

## 🎯 模块定位

LLM 客户端模块负责统一管理所有 LLM 调用，屏蔽不同提供商的差异，提供：
- 统一的调用接口
- 延迟初始化（按需加载）
- 多维度限流
- 自动重试和降级
- 流式输出支持
- 成本统计和追踪

### 模块边界说明

| 模块 | 职责 | 特点 | 适用场景 |
|------|------|------|----------|
| **llm** | 基础模型调用（chat、embed） | 通用对话、嵌入 | 直接调用 OpenAI/Anthropic/DeepSeek |
| **mcp** | 标准化工具调用协议 | 工具发现、调用、结果解析 | 统一外部工具调用 |

### LLM 与 MCP 的关系

```
┌─────────────┐     工具调用      ┌─────────────┐
│    LLM      │ ───────────────► │    MCP      │
│ (chat/embed)│   tools 参数     │ (工具协议)  │
└─────────────┘                  └─────────────┘
       │                                │
       │   模型返回工具调用请求          │
       ▼                                ▼
┌─────────────┐                  ┌─────────────┐
│  应用层     │                  │ MCP Server  │
│ 解析并执行  │                  │ (外部工具)   │
└─────────────┘                  └─────────────┘
```

- `llm/` 提供 `chat(..., tools=...)` 方法，模型可返回工具调用请求
- 应用层解析工具调用后，可通过 `mcp/` 模块执行标准化工具调用
- `mcp/` 也可以独立使用，直接调用 MCP Server 的工具

---

## 🏗️ 核心架构

### 三层架构

```
┌─────────────────────────────────────────┐
│          接口层 (base.py)              │
│  LLMClient - 统一调用接口               │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│        实现层 (providers/)              │
│  OpenAI / Anthropic / DeepSeek / Local   │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│        工厂层 (factory.py)              │
│  create_llm_client(config)              │
└─────────────────────────────────────────┘
```

---

## 📖 核心接口

### LLMClient 接口

**位置**：`infra/llm/base.py`

```python
from abc import ABC, abstractmethod
from typing import List, AsyncIterator
from dataclasses import dataclass

@dataclass
class Message:
    """消息对象"""
    role: str           # system, user, assistant
    content: str        # 消息内容
    name: Optional[str] # 可选的名称

@dataclass
class ChatRequest:
    """对话请求"""
    model: str                    # 模型名称
    messages: List[Message]       # 消息列表
    temperature: float = 0.7      # 温度参数
    max_tokens: Optional[int]     # 最大Token数
    top_p: float = 1.0           # Top-p采样
    stream: bool = False          # 是否流式输出
    stop: Optional[List[str]]     # 停止词
    tools: Optional[List[dict]]   # 工具定义

@dataclass
class ChatResponse:
    """对话响应"""
    id: str                        # 响应ID
    model: str                     # 模型名称
    content: str                   # 响应内容
    role: str = "assistant"        # 角色
    usage: dict                    # Token使用量
    finish_reason: str = "stop"    # 完成原因
    latency: float = 0.0          # 延迟时间

@dataclass
class StreamChunk:
    """流式响应块"""
    content: str      # 增量内容
    finish_reason: Optional[str]  # 完成原因

class LLMClient(ABC):
    """LLM客户端统一接口"""
    
    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        """同步对话接口"""
        pass
    
    @abstractmethod
    async def achat(self, request: ChatRequest) -> ChatResponse:
        """异步对话接口"""
        pass
    
    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """流式对话接口"""
        pass
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """文本向量化接口"""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """统计Token数量"""
        pass
```

---

## 🏭 工厂函数

### create_llm_client

**位置**：`infra/llm/factory.py`

```python
from infra.llm.base import LLMClient
from infra.llm.providers.openai import OpenAIClient
from infra.llm.providers.anthropic import AnthropicClient
from infra.llm.providers.deepseek import DeepSeekClient
from infra.llm.providers.local import LocalClient

@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str          # openai, anthropic, deepseek, local
    model: str             # 模型名称
    api_key_env: str       # API密钥环境变量名
    timeout: int = 30      # 超时时间
    max_retries: int = 3   # 最大重试次数
    
    # 限流配置
    rate_limit: dict = None
    
    # 模型参数
    default_params: dict = None

def create_llm_client(config: LLMConfig) -> LLMClient:
    """
    根据配置创建LLM客户端
    
    参数说明：
        provider: LLM提供商（openai, anthropic, deepseek, local）
        model: 模型名称（gpt-4, claude-3-opus, deepseek-chat等）
        api_key_env: 环境变量名（不直接存储API密钥）
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        rate_limit: 限流配置
        default_params: 默认参数
    
    返回：
        LLMClient实例
    
    示例：
        config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key_env="OPENAI_API_KEY",
            timeout=30,
            max_retries=3
        )
        llm = create_llm_client(config)
    """
    if config.provider == "openai":
        return OpenAIClient(config)
    elif config.provider == "anthropic":
        return AnthropicClient(config)
    elif config.provider == "deepseek":
        return DeepSeekClient(config)
    elif config.provider == "local":
        return LocalClient(config)
    else:
        raise ValueError(f"Unknown provider: {config.provider}")
```

---

## ⚙️ 关键设计

### 1. 延迟初始化（Deferred Initialization）

**问题**：启动时加载所有LLM客户端会导致启动缓慢和资源浪费

**解决方案**：延迟初始化 - 使用时才加载

```python
class OpenAIClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None  # 延迟初始化
        self._metrics = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_latency": 0.0,
        }
    
    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is None:
            import os
            from openai import OpenAI
            
            # 从环境变量读取API密钥
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                raise ValueError(f"环境变量 {self.config.api_key_env} 未设置")
            
            # 创建客户端
            self._client = OpenAI(
                api_key=api_key,
                timeout=self.config.timeout
            )
            
            logger.info(f"LLM客户端初始化: provider={self.config.provider}, model={self.config.model}")
        
        return self._client
    
    def chat(self, request: ChatRequest) -> ChatResponse:
        """同步对话"""
        client = self._get_client()  # 延迟初始化
        
        start_time = time.time()
        try:
            # 调用OpenAI API
            response = client.chat.completions.create(
                model=request.model,
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                tools=request.tools
            )
            
            # 统计指标
            self._update_metrics(response.usage, time.time() - start_time)
            
            return ChatResponse(
                id=response.id,
                model=response.model,
                content=response.choices[0].message.content,
                usage=response.usage,
                finish_reason=response.choices[0].finish_reason
            )
            
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise
```

**优点**：
- ✅ 按需加载，启动快速
- ✅ 未使用的客户端不占用资源
- ✅ 支持灵活的配置更新

**使用示例**：
```python
# 创建客户端（不立即初始化）
config = LLMConfig(provider="openai", model="gpt-4", api_key_env="OPENAI_API_KEY")
llm = create_llm_client(config)

# 第一次调用时才初始化OpenAI SDK
response = llm.chat([Message(role="user", content="你好")])  # 这里才初始化
```

---

### 2. 多维度限流（Multi-dimensional Rate Limiting）

**问题**：不同模型有不同的限流需求，需要支持：
- 并发限流
- Token限流
- 模型级别限流

**解决方案**：多维度限流器

```python
from threading import Lock
from asyncio import Semaphore

class MultiLimiter:
    """多维度限流器"""
    
    def __init__(self):
        # 并发限流
        self.concurrent_limit = Semaphore(10)
        
        # Token限流（令牌桶算法）
        self.token_bucket = TokenBucket(
            capacity=100000,
            refill_rate=1000,  # tokens per second
            enabled=True
        )
        
        # 模型级别限流（不使用并发限制）
        self.model_limiters = {}
        
        # 线程安全
        self._lock = Lock()
    
    def register_model(self, model: str, tokens_per_minute: int, requests_per_minute: int):
        """注册模型级别的限流器"""
        with self._lock:
            self.model_limiters[model] = {
                "token_limiter": TokenBucket(tokens_per_minute / 60.0),
                "request_limiter": TokenBucket(requests_per_minute / 60.0)
            }
    
    async def acquire(self, model: str, tokens: int):
        """获取限流许可"""
        # 1. 等待并发限流
        await self.concurrent_limit.acquire()
        
        # 2. 等待Token限流
        self.token_bucket.consume(tokens)
        
        # 3. 等待模型级别限流
        if model in self.model_limiters:
            self.model_limiters[model]["token_limiter"].consume(tokens)
            self.model_limiters[model]["request_limiter"].consume(1)
    
    def release(self):
        """释放并发许可"""
        self.concurrent_limit.release()
```

**配置示例**：
```yaml
# config/infra/development.yaml
llm:
  rate_limit:
    # 全局并发
    max_concurrent: 10
    
    # 全局Token限流
    tokens_per_minute: 100000
    
    # 模型级别限流
    models:
      gpt-4:
        tokens_per_minute: 50000
        requests_per_minute: 100
      gpt-3.5-turbo:
        tokens_per_minute: 100000
        requests_per_minute: 500
```

---

### 3. 配置变更通知（Configuration Change Notification）

**问题**：配置变更无法实时生效，需要重启服务

**解决方案**：发布/订阅模式通知配置变更

```python
from typing import Callable, List
from threading import RLock
import json
from pathlib import Path

class LLMConfigNotifier:
    """LLM配置变更通知器"""
    
    def __init__(self):
        self._handlers: List[Callable] = []
        self._lock = RLock()
    
    def subscribe(self, handler: Callable):
        """订阅配置变更"""
        with self._lock:
            self._handlers.append(handler)
    
    def unsubscribe(self, handler: Callable):
        """取消订阅"""
        with self._lock:
            self._handlers.remove(handler)
    
    def notify(self, event: dict):
        """通知配置变更"""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"配置变更通知失败: {e}")

class LLMConfigManager:
    """LLM配置管理器"""
    
    _instance = None
    _notifier = LLMConfigNotifier()
    
    def __init__(self, config_file: str = "config/llm_config.json"):
        self.config_file = Path(config_file)
        self._configs = {}
        self._default_provider = None
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        if self.config_file.exists():
            with open(self.config_file) as f:
                data = json.load(f)
                self._configs = data.get("providers", {})
                self._default_provider = data.get("default_provider")
    
    def get_config(self, provider: str = None) -> dict:
        """获取配置"""
        provider = provider or self._default_provider
        if provider not in self._configs:
            raise ValueError(f"Unknown provider: {provider}")
        return self._configs[provider]
    
    def update_config(self, provider: str, config: dict):
        """更新配置并通知"""
        with open(self.config_file) as f:
            data = json.load(f)
        
        # 更新配置
        data["providers"][provider] = config
        data["providers"][provider]["updated_at"] = datetime.now().isoformat()
        
        # 保存配置
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        # 通知订阅者
        self._notifier.notify({
            "event": "config_updated",
            "provider": provider,
            "config": config
        })
        
        # 更新内存配置
        self._configs[provider] = config
```

**使用示例**：
```python
# 订阅配置变更
def on_config_change(event):
    print(f"配置变更: {event['provider']}")
    # 更新LLM客户端

config_manager = LLMConfigManager()
config_manager._notifier.subscribe(on_config_change)

# 更新配置（自动通知订阅者）
config_manager.update_config("openai", {
    "model": "gpt-4-turbo",
    "temperature": 0.8
})
```

---

### 4. 自动重试和降级（Retry and Fallback）

**问题**：LLM调用可能失败，需要自动重试和降级

**解决方案**：指数退避重试 + 降级到备用模型

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class OpenAIClient(LLMClient):
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def chat_with_retry(self, request: ChatRequest) -> ChatResponse:
        """带重试的对话"""
        try:
            return self.chat(request)
        except RateLimitError:
            # 限流错误，等待后重试
            logger.warning("触发限流，等待后重试")
            raise
        except APIConnectionError:
            # 连接错误，可能是临时网络问题
            logger.warning("连接失败，重试中")
            raise
        except Exception as e:
            # 其他错误，不重试
            logger.error(f"LLM调用失败: {e}")
            raise
    
    def chat_with_fallback(self, request: ChatRequest, fallback_model: str = None) -> ChatResponse:
        """带降级的对话"""
        try:
            return self.chat_with_retry(request)
        except Exception as e:
            if fallback_model:
                logger.warning(f"主模型失败，降级到 {fallback_model}")
                request.model = fallback_model
                return self.chat(request)
            else:
                raise
```

**配置示例**：
```yaml
llm:
  retry:
    max_attempts: 3
    backoff_factor: 2
    retry_on:
      - RateLimitError
      - APIConnectionError
  
  fallback:
    enabled: true
    fallback_chain:
      - gpt-4
      - gpt-3.5-turbo
      - deepseek-chat
```

---

### 5. 内置指标收集（Built-in Metrics）

**问题**：需要追踪LLM调用的成本、延迟、Token使用量

**解决方案**：自动收集指标

```python
class OpenAIClient(LLMClient):
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost": 0.0,
            "total_latency": 0.0,
            "avg_latency": 0.0,
        }
    
    def _update_metrics(self, usage: dict, latency: float, success: bool):
        """更新指标"""
        self._metrics["total_requests"] += 1
        
        if success:
            self._metrics["successful_requests"] += 1
            self._metrics["total_tokens"] += usage.get("total_tokens", 0)
            self._metrics["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self._metrics["completion_tokens"] += usage.get("completion_tokens", 0)
            
            # 计算成本
            cost = self._calculate_cost(usage)
            self._metrics["total_cost"] += cost
        
        else:
            self._metrics["failed_requests"] += 1
        
        self._metrics["total_latency"] += latency
        self._metrics["avg_latency"] = self._metrics["total_latency"] / self._metrics["total_requests"]
    
    def _calculate_cost(self, usage: dict) -> float:
        """计算成本"""
        # OpenAI价格（2024年）
        prices = {
            "gpt-4": {"prompt": 0.03 / 1000, "completion": 0.06 / 1000},
            "gpt-4-turbo": {"prompt": 0.01 / 1000, "completion": 0.03 / 1000},
            "gpt-3.5-turbo": {"prompt": 0.0015 / 1000, "completion": 0.002 / 1000},
        }
        
        model_prices = prices.get(self.config.model, {"prompt": 0, "completion": 0})
        
        prompt_cost = usage.get("prompt_tokens", 0) * model_prices["prompt"]
        completion_cost = usage.get("completion_tokens", 0) * model_prices["completion"]
        
        return prompt_cost + completion_cost
    
    def get_metrics(self) -> dict:
        """获取指标"""
        return self._metrics.copy()
```

---

## 🚀 使用示例

### 基本使用

```python
from infra.llm import create_llm_client
from infra.llm.base import Message, ChatRequest
from infra.config import load_config

# 加载配置
config = load_config("config/infra/development.yaml")

# 创建客户端（延迟初始化）
llm = create_llm_client(config.llm)

# 同步对话
response = llm.chat(ChatRequest(
    model="gpt-4",
    messages=[
        Message(role="system", content="你是一个助手"),
        Message(role="user", content="你好")
    ]
))
print(response.content)

# 异步对话
response = await llm.achat(ChatRequest(
    model="gpt-4",
    messages=[Message(role="user", content="你好")]
))

# 流式输出
async for chunk in llm.stream_chat(ChatRequest(
    model="gpt-4",
    messages=[Message(role="user", content="讲一个故事")],
    stream=True
)):
    print(chunk.content, end="", flush=True)

# 文本向量化
embeddings = await llm.embed(["hello world", "goodbye"])
print(len(embeddings[0]))  # 向量维度

# Token统计
token_count = llm.count_tokens("这是一段测试文本")
print(f"Token数量: {token_count}")
```

### 带重试和降级

```python
# 带重试的对话
response = llm.chat_with_retry(ChatRequest(
    model="gpt-4",
    messages=[Message(role="user", content="你好")]
))

# 带降级的对话
response = llm.chat_with_fallback(
    ChatRequest(model="gpt-4", messages=[...]),
    fallback_model="gpt-3.5-turbo"
)
```

### 获取指标

```python
# 获取成本统计
metrics = llm.get_metrics()
print(f"总请求数: {metrics['total_requests']}")
print(f"成功率: {metrics['successful_requests'] / metrics['total_requests']}")
print(f"总成本: ${metrics['total_cost']:.4f}")
print(f"平均延迟: {metrics['avg_latency']:.2f}s")
```

### 配置变更通知

```python
# 订阅配置变更
config_manager = LLMConfigManager()

def on_config_change(event):
    print(f"配置变更: {event['provider']}")
    # 更新LLM客户端
    llm.update_config(event['config'])

config_manager._notifier.subscribe(on_config_change)

# 更新配置
config_manager.update_config("openai", {
    "model": "gpt-4-turbo",
    "temperature": 0.7
})
```

---

## 📊 性能优化

### 连接池管理

```yaml
llm:
  connection_pool:
    max_connections: 100         # 最大连接数
    max_keepalive_connections: 20 # 最大保活连接数
    keepalive_expiry: 30          # 保活过期时间(秒)
```

### 异步批量调用

```python
# 批量异步调用
async def batch_chat(messages_list: List[List[Message]]):
    tasks = [
        llm.achat(ChatRequest(model="gpt-3.5-turbo", messages=messages))
        for messages in messages_list
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    return responses
```

---

## 🔧 配置参考

### 完整配置示例

```yaml
# config/infra/production.yaml
llm:
  # OpenAI配置
  openai:
    provider: openai
    model: gpt-4
    api_key_env: OPENAI_API_KEY
    timeout: 30
    max_retries: 3
    
    # 限流配置
    rate_limit:
      max_concurrent: 10
      tokens_per_minute: 50000
      requests_per_minute: 100
    
    # 模型参数
    default_params:
      temperature: 0.7
      max_tokens: 2000
      top_p: 1.0
    
    # 重试配置
    retry:
      max_attempts: 3
      backoff_factor: 2
    
    # 降级配置
    fallback:
      enabled: true
      fallback_chain:
        - gpt-4-turbo
        - gpt-3.5-turbo
  
  # Anthropic配置
  anthropic:
    provider: anthropic
    model: claude-3-opus
    api_key_env: ANTHROPIC_API_KEY
    timeout: 60
    max_retries: 2
  
  # DeepSeek配置
  deepseek:
    provider: deepseek
    model: deepseek-chat
    api_key_env: DEEPSEEK_API_KEY
    timeout: 30
  
  # 本地模型配置
  local:
    provider: local
    model_path: /models/llama-2-7b
    device: cuda:0
    max_tokens: 2000
```

---

## 📁 文件结构

```
infra/llm/
├── __init__.py               # 模块导出
├── base.py                   # LLMClient 接口
├── factory.py                # create_llm_client()
├── schemas.py                # 数据模型
├── cost_tracker.py          # 成本追踪
└── providers/
    ├── openai.py           # OpenAI 实现
    ├── anthropic.py        # Anthropic 实现
    ├── deepseek.py         # DeepSeek 实现
    └── local.py            # 本地模型实现
```

---

## 🔗 相关文档

- [配置管理](../config/index.md) - 配置加载和管理
- [向量存储](../vector/index.md) - 向量嵌入接口
- [数据库](../database/index.md) - 数据库操作

---

*最后更新: 2026-04-11*