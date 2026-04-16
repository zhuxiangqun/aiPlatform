# 缓存模块（设计真值：以代码事实为准）

> 说明：缓存模块的 As-Is 能力以 `infra/cache/*` 代码与测试为准；文档中的后端/策略若未实现需标注为 To-Be。

> 提供缓存抽象层，支持多种缓存后端（Redis/内存/文件）

---

## 🎯 模块定位

缓存模块负责统一管理所有缓存数据，支持：
- 多缓存后端
- TTL 过期策略
- 缓存模式（LRU/LFU/FIFO）
- 分布式缓存
- 缓存统计

> **注意**：缓存模块与 memory 模块的区别：
> - **memory**：底层内存管理（内存池、OOM 防护、显存管理）
> - **cache**：应用层缓存（Redis、内存缓存、文件缓存）

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
cache:
  type: redis                    # redis, memory, file
  host: localhost
  port: 6379
  password: ${REDIS_PASSWORD}
  db: 0
  
  # 连接池配置
  pool:
    max_connections: 50
    retry_on_timeout: true
    socket_timeout: 5
    socket_connect_timeout: 5
  
  # 缓存策略
  strategy:
    default_ttl: 3600            # 默认 TTL（秒）
    max_entries: 10000           # 最大条目数
    eviction_policy: lru         # lru, lfu, fifo
  
  # 前缀
  key_prefix: "ai-platform:"
  
  # 延迟初始化
  lazy_init: true
```

---

## 📖 核心接口定义

### CacheClient 接口

**位置**：`infra/cache/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get` | `key: str` | `Optional[Any]` | 获取缓存 |
| `set` | `key: str`, `value: Any`, `ttl: int` | `bool` | 设置缓存 |
| `delete` | `key: str` | `bool` | 删除缓存 |
| `exists` | `key: str` | `bool` | 检查存在 |
| `clear` | 无 | `None` | 清空缓存 |
| `keys` | `pattern: str` | `List[str]` | 模式匹配 |
| `expire` | `key: str`, `ttl: int` | `bool` | 设置过期时间 |
| `ttl` | `key: str` | `int` | 获取剩余 TTL |

### CacheManager 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_or_set` | `key: str`, `factory: Callable`, `ttl: int` | `Any` | 获取或设置 |
| `get_many` | `keys: List[str]` | `Dict[str, Any]` | 批量获取 |
| `set_many` | `items: Dict[str, Any]`, `ttl: int` | `None` | 批量设置 |
| `delete_many` | `keys: List[str]` | `None` | 批量删除 |
| `get_stats` | 无 | `CacheStats` | 获取统计信息 |

---

## 🏭 工厂函数

### create_cache_client

**位置**：`infra/cache/factory.py`

**函数签名**：

```python
def create_cache_client(
    config: CacheConfig
) -> CacheClient:
    """
    创建缓存客户端

    参数：
        config: 缓存配置

    返回：
        CacheClient 实例
    """
```

**使用示例**：

```python
from infra.cache import create_cache_client, CacheConfig

# Redis 缓存
cache = create_cache_client(CacheConfig(
    type="redis",
    host="localhost",
    port=6379,
    key_prefix="ai-platform:"
))

# 设置缓存
await cache.set("user:1", {"name": "Alice"}, ttl=1800)
await cache.set("user:2", {"name": "Bob"}, ttl=3600)

# 获取缓存
user = await cache.get("user:1")
print(user)  # {"name": "Alice"}

# 批量操作
await cache.set_many({
    "config:theme": "dark",
    "config:language": "zh-CN"
}, ttl=86400)

configs = await cache.get_many(["config:theme", "config:language"])
```

---

## 📊 数据模型

### CacheConfig

```python
@dataclass
class CacheConfig:
    type: str = "redis"          # redis, memory, file
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    pool: Optional[PoolConfig] = None
    strategy: Optional[StrategyConfig] = None
    key_prefix: str = ""
    lazy_init: bool = True

@dataclass
class PoolConfig:
    max_connections: int = 50
    retry_on_timeout: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5

@dataclass
class StrategyConfig:
    default_ttl: int = 3600
    max_entries: int = 10000
    eviction_policy: str = "lru"
```

### CacheStats

```python
@dataclass
class CacheStats:
    hits: int
    misses: int
    keys: int
    used_memory: int
    hit_rate: float
```

---

## 🚀 使用示例

### 基本操作

```python
from infra.cache import create_cache_client

cache = create_cache_client(CacheConfig(
    type="redis",
    host="localhost"
))

# 设置缓存
await cache.set("key1", "value1", ttl=60)
await cache.set("key2", {"name": "Alice"}, ttl=3600)

# 获取缓存
value = await cache.get("key1")
print(value)  # "value1"

# 检查存在
exists = await cache.exists("key1")
print(exists)  # True

# 设置过期时间
await cache.expire("key1", 120)

# 获取剩余 TTL
ttl = await cache.ttl("key1")
print(ttl)  # 120

# 删除
await cache.delete("key1")

# 清空所有
await cache.clear()
```

### 模式匹配

```python
# 匹配所有用户 key
keys = await cache.keys("user:*")
print(keys)  # ["user:1", "user:2", "user:3"]

# 匹配所有配置 key
config_keys = await cache.keys("config:*")

# 批量删除匹配到的 key
await cache.delete_many(keys)
```

### 缓存管理器

```python
from infra.cache import create_cache_client, CacheManager

cache = create_cache_client(CacheConfig(type="redis"))
manager = CacheManager(cache)

# get_or_set：获取或设置
user = await manager.get_or_set(
    "user:1",
    lambda: fetch_user_from_db(1),  # 只有缓存不存在时调用
    ttl=3600
)

# 批量操作
items = await manager.get_many(["key1", "key2", "key3"])
await manager.set_many(
    {"key1": "value1", "key2": "value2"},
    ttl=60
)

# 统计信息
stats = await manager.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Keys: {stats.keys}")
print(f"Memory: {stats.used_memory / 1024 / 1024:.2f} MB")
```

### 缓存装饰器

```python
from infra.cache import cached, create_cache_client

cache = create_cache_client(CacheConfig(type="redis"))

# 使用装饰器
@cached(prefix="user:", ttl=300)
async def get_user(user_id: int):
    """用户查询（带缓存）"""
    return await db.query("SELECT * FROM users WHERE id = ?", user_id)

# 调用时会自动缓存结果
user1 = await get_user(1)  # 从数据库查询
user2 = await get_user(1)  # 从缓存获取
```

---

## 🔧 扩展指南

### 添加新的缓存后端

**文件**：`infra/cache/memcached.py`

```python
from infra.cache.base import CacheClient

class MemcachedClient(CacheClient):
    """Memcached 客户端"""
    
    def __init__(self, config: CacheConfig):
        import pymemcache
        self.client = pymemcache.Client(
            (config.host, config.port),
            connect_timeout=config.pool.socket_connect_timeout,
            timeout=config.pool.socket_timeout
        )
    
    async def get(self, key: str) -> Optional[Any]:
        return self.client.get(key)
    
    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        return self.client.set(key, value, expire=ttl)
    
    async def delete(self, key: str) -> bool:
        return self.client.delete(key)
    
    async def exists(self, key: str) -> bool:
        return self.client.get(key) is not None
    
    async def clear(self) -> None:
        # Memcached 不支持 clear，需要逐个删除
        pass
    
    async def keys(self, pattern: str) -> List[str]:
        # Memcached 不支持 keys 模式匹配
        return []
```

### 注册到工厂

```python
def create_cache_client(config: CacheConfig) -> CacheClient:
    if config.type == "redis":
        return RedisClient(config)
    elif config.type == "memory":
        return MemoryClient(config)
    elif config.type == "file":
        return FileClient(config)
    elif config.type == "memcached":
        return MemcachedClient(config)
    else:
        raise ValueError(f"Unknown cache type: {config.type}")
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `cache.type` | redis/memory/file/memcached | invalid type |
| `cache.port` | 1-65535 | must be 1-65535 |
| `cache.db` | 0-15 | must be 0-15 |
| `cache.strategy.default_ttl` | > 0 | must be > 0 |
| `cache.strategy.eviction_policy` | lru/lfu/fifo | invalid policy |

---

## 📁 文件结构

```
infra/cache/
├── __init__.py                # 模块导出
├── base.py                   # CacheClient 接口
├── factory.py                # create_cache_client()
├── schemas.py                # 数据模型
├── redis_client.py           # Redis 实现
├── memory_client.py          # 内存实现
├── file_client.py           # 文件实现
└── manager.py               # CacheManager
```

---

*最后更新: 2026-04-11*

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/cache/*`
