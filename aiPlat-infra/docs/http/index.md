# HTTP 客户端模块

> 提供 HTTP 客户端抽象，支持重试、超时、连接池、代理等能力

---

## 🎯 模块定位

HTTP 客户端模块负责统一管理所有 HTTP 请求，支持：
- 同步/异步请求
- 连接池管理
- 自动重试
- 超时控制
- 代理支持
- 响应缓存

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
http:
  # 超时配置
  timeout:
    connect: 10        # 连接超时（秒）
    read: 30           # 读取超时（秒）
    write: 30          # 写入超时（秒）
    pool: 5            # 池超时（秒）
  
  # 重试配置
  retry:
    enabled: true
    max_attempts: 3
    backoff_factor: 2
    retry_on_status: [429, 500, 502, 503, 504]
  
  # 连接池配置
  pool:
    max_connections: 100
    max_keepalive_connections: 20
    keepalive_expiry: 30
  
  # 代理配置
  proxy:
    http: ${HTTP_PROXY}
    https: ${HTTPS_PROXY}
  
  # 默认请求头
  headers:
    User-Agent: ai-platform/1.0
    Accept: application/json
  
  # 响应缓存
  cache:
    enabled: true
    ttl: 300
```

---

## 📖 核心接口定义

### HTTPClient 接口

**位置**：`infra/http/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get` | `url: str`, `**kwargs` | `Response` | GET 请求 |
| `post` | `url: str`, `**kwargs` | `Response` | POST 请求 |
| `put` | `url: str`, `**kwargs` | `Response` | PUT 请求 |
| `patch` | `url: str`, `**kwargs` | `Response` | PATCH 请求 |
| `delete` | `url: str`, `**kwargs` | `Response` | DELETE 请求 |
| `head` | `url: str`, `**kwargs` | `Response` | HEAD 请求 |
| `options` | `url: str`, `**kwargs` | `Response` | OPTIONS 请求 |
| `request` | `method: str`, `url: str`, `**kwargs` | `Response` | 通用请求方法 |
| `close` | 无 | `None` | 关闭客户端 |

### AsyncHTTPClient 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get` | `url: str`, `**kwargs` | `Response` | 异步 GET 请求 |
| `post` | `url: str`, `**kwargs` | `Response` | 异步 POST 请求 |
| `put` | `url: str`, `**kwargs` | `Response` | 异步 PUT 请求 |
| `delete` | `url: str`, `**kwargs` | `Response` | 异步 DELETE 请求 |
| `request` | `method: str`, `url: str`, `**kwargs` | `Response` | 异步通用请求 |
| `aclose` | 无 | `None` | 异步关闭客户端 |

### Response 对象

**位置**：`infra/http/response.py`

| 属性 | 类型 | 说明 |
|------|------|------|
| `status_code` | int | HTTP 状态码 |
| `text` | str | 响应文本 |
| `json()` | dict | 解析 JSON 响应 |
| `content` | bytes | 响应字节内容 |
| `headers` | dict | 响应头 |
| `cookies` | dict | 响应 cookies |
| `elapsed` | timedelta | 请求耗时 |

---

## 🏭 工厂函数

### create_http_client

**位置**：`infra/http/factory.py`

**函数签名**：

```python
def create_http_client(
    config: Optional[HTTPConfig] = None,
    async_mode: bool = False
) -> Union[HTTPClient, AsyncHTTPClient]:
    """
    创建 HTTP 客户端

    参数：
        config: HTTP 配置（可选）
        async_mode: 是否创建异步客户端

    返回：
        HTTPClient 或 AsyncHTTPClient 实例
    """
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config.timeout.connect` | int | 10 | 连接超时（秒） |
| `config.timeout.read` | int | 30 | 读取超时（秒） |
| `config.retry.max_attempts` | int | 3 | 最大重试次数 |
| `config.retry.backoff_factor` | float | 2.0 | 退避因子 |
| `config.pool.max_connections` | int | 100 | 最大连接数 |
| `config.proxy.http` | str | None | HTTP 代理 |
| `config.proxy.https` | str | None | HTTPS 代理 |

**使用示例**：

```python
from infra.http import create_http_client

# 同步客户端
http = create_http_client()
response = http.get("https://api.example.com/data")
print(response.json())

# 异步客户端
async_http = create_http_client(async_mode=True)
response = await async_http.get("https://api.example.com/data")
print(response.json())
```

---

## 📊 数据模型

### HTTPConfig

```python
@dataclass
class HTTPConfig:
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    pool: PoolConfig = field(default_factory=PoolConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    headers: Dict[str, str] = field(default_factory=dict)
    cache: CacheConfig = field(default_factory=CacheConfig)
```

### TimeoutConfig

```python
@dataclass
class TimeoutConfig:
    connect: int = 10
    read: int = 30
    write: int = 30
    pool: int = 5
```

### RetryConfig

```python
@dataclass
class RetryConfig:
    enabled: bool = True
    max_attempts: int = 3
    backoff_factor: float = 2.0
    retry_on_status: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
```

---

## 🚀 使用示例

### 基本请求

```python
from infra.http import create_http_client

http = create_http_client()

# GET 请求
response = http.get("https://api.example.com/users")
print(response.status_code)
print(response.json())

# POST 请求
response = http.post(
    "https://api.example.com/users",
    json={"name": "Alice", "email": "alice@example.com"}
)
print(response.json())

# 带查询参数的 GET
response = http.get(
    "https://api.example.com/search",
    params={"q": "python", "page": 1}
)

# 带自定义头
response = http.get(
    "https://api.example.com/protected",
    headers={"Authorization": "Bearer token123"}
)
```

### 重试机制

```python
from infra.http import create_http_client, HTTPConfig, RetryConfig

# 配置重试
config = HTTPConfig(
    retry=RetryConfig(
        enabled=True,
        max_attempts=5,
        backoff_factor=1.5,
        retry_on_status=[429, 500, 502, 503, 504]
    )
)

http = create_http_client(config)

# 自动重试（指数退避）
# 第一次重试：1s, 第二次：1.5s, 第三次：2.25s, ...
response = http.get("https://api.example.com/data")
```

### 代理配置

```python
from infra.http import create_http_client, HTTPConfig, ProxyConfig

config = HTTPConfig(
    proxy=ProxyConfig(
        http="http://proxy.example.com:8080",
        https="http://proxy.example.com:8080"
    )
)

http = create_http_client(config)
response = http.get("https://api.example.com/data")
```

### 异步请求

```python
import asyncio
from infra.http import create_http_client

async def fetch_data():
    http = create_http_client(async_mode=True)
    
    # 并发请求
    results = await asyncio.gather(
        http.get("https://api.example.com/users"),
        http.get("https://api.example.com/posts"),
        http.get("https://api.example.com/comments")
    )
    
    for response in results:
        print(response.status_code, response.json())
    
    await http.aclose()

asyncio.run(fetch_data())
```

### 流式响应

```python
from infra.http import create_http_client

http = create_http_client()

# 流式下载大文件
with http.stream("GET", "https://example.com/largefile") as response:
    with open("largefile", "wb") as f:
        for chunk in response.iter_bytes(chunk_size=8192):
            f.write(chunk)
```

---

## 🔧 扩展指南

### 添加新的 HTTP 中间件

**文件**：`infra/http/middleware/logging.py`

```python
from infra.http.base import HTTPClient
from infra.http.response import Response

class LoggingMiddleware:
    """日志中间件"""
    
    def __init__(self, client: HTTPClient):
        self.client = client
    
    def get(self, url: str, **kwargs) -> Response:
        start = time.time()
        response = self.client.get(url, **kwargs)
        elapsed = time.time() - start
        
        logger.info(f"GET {url} -> {response.status_code} ({elapsed:.3f}s)")
        return response
```

### 添加新的 HTTP 实现

```python
from infra.http.base import HTTPClient
from infra.http.response import Response

class AioHttpClient(HTTPClient):
    """基于 aiohttp 的客户端实现"""
    
    def __init__(self, config: HTTPConfig):
        import aiohttp
        self.session = aiohttp.ClientSession()
    
    def get(self, url: str, **kwargs) -> Response:
        # 实现逻辑
        pass
    
    def close(self):
        asyncio.run(self.session.close())
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `http.timeout.connect` | > 0 整数 | must be > 0 |
| `http.timeout.read` | > 0 整数 | must be > 0 |
| `http.retry.max_attempts` | 1-10 整数 | must be 1-10 |
| `http.pool.max_connections` | > 0 整数 | must be > 0 |

---

## 📁 文件结构

```
infra/http/
├── __init__.py               # 模块导出
├── base.py                   # HTTPClient 接口
├── factory.py                # create_http_client()
├── response.py               # Response 对象
├── schemas.py               # 数据模型
├── httpx_client.py           # httpx 实现
└── aiohttp_client.py       # aiohttp 实现
```

---

*最后更新: 2026-04-11*