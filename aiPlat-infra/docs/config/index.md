# 配置管理模块（设计真值：以代码事实为准）

> 说明：本文档包含较多 To-Be 的“配置中心/热更新”能力描述。As-Is 以 infra 实际提供的 config loader 与 schema 为准（若未实现，则标注为规划项）。

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/config/*`

> 提供多源配置加载、环境变量覆盖、动态配置更新等能力

---

## 🎯 模块定位

配置管理模块负责统一管理所有配置，支持：
- 多配置源（文件、环境变量、配置中心）
- 配置优先级和覆盖
- 配置变更通知
- 动态配置热更新
- 配置验证和类型转换

---

## ⚙️ 配置文件结构

### 默认配置文件

**位置**：`config/infra/default.yaml`

```yaml
# 数据库配置
database:
  type: postgres                    # postgres, mysql, mongodb
  host: localhost
  port: 5432
  name: ai_platform
  user: ${DB_USER}                  # 从环境变量读取
  password: ${DB_PASSWORD}          # 从环境变量读取
  
  # 连接池配置
  pool:
    min_size: 5
    max_size: 20
    max_overflow: 10
    pool_timeout: 30
    recycle: 3600
  
  # SSL配置
  ssl:
    enabled: false
    cert_path: /etc/ssl/certs/db-cert.pem
  
  # 延迟初始化
  lazy_init: true                   # 启用延迟初始化

# LLM配置
llm:
  provider: openai
  model: gpt-4
  api_key_env: OPENAI_API_KEY      # 环境变量名（不直接存储密钥）
  timeout: 30
  max_retries: 3
  
  # 延迟初始化
  lazy_init: true
  
  # 限流配置（多维度）
  rate_limit:
    max_concurrent: 10
    tokens_per_minute: 100000
    models:
      gpt-4:
        tokens_per_minute: 50000
        requests_per_minute: 100
  
  # 模型参数
  default_params:
    temperature: 0.7
    max_tokens: 2000
  
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
  
  # 指标收集
  metrics:
    enabled: true
    track_cost: true
    track_latency: true

# 向量存储配置
vector:
  type: milvus
  host: localhost
  port: 19530
  dimension: 1536
  
  index:
    type: HNSW
    params:
      m: 16
      ef_construction: 256
  
  lazy_init: true                  # 延迟初始化

# 缓存配置
cache:
  type: redis
  host: localhost
  port: 6379
  password: ${REDIS_PASSWORD}
  db: 0
  
  pool:
    max_connections: 50
  
  lazy_init: true

# 日志配置
logging:
  level: ${LOG_LEVEL:INFO}        # 支持环境变量+默认值
  format: json
  
  output:
    - console
    - file
  
  file:
    path: /var/log/ai-platform/infra.log
    max_size: 100MB
    backup_count: 10

# 监控配置
monitoring:
  enabled: true
  port: 9090
  
  metrics:
    prefix: ai_platform_infra
  
  health_check:
    enabled: true
    path: /health
```

---

## 📖 核心接口定义

### ConfigLoader 接口

**位置**：`infra/config/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `load` | `path: Optional[str]` | `Config` | 加载配置，自动合并多源 |
| `reload` | 无 | `Config` | 热加载配置 |
| `watch` | `callback: Callable` | `None` | 监听配置变更 |

**支持的环境变量前缀**：
- `INFRA_`：基础设施配置（如 `INFRA_LLM_MODEL`）
- `DB_` / `DATABASE_`：数据库配置（如 `DB_HOST`）
- `LLM_`：LLM配置（如 `LLM_API_KEY`）
- `REDIS_`：Redis配置（如 `REDIS_PASSWORD`）

**实现类**：`ConfigLoaderImpl` 位于 `infra/config/loader.py`

---

### Config 对象

**位置**：`infra/config/config.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get` | `key: str, default: Any = None` | `Any` | 获取配置项，支持点号路径 |
| `set` | `key: str, value: Any` | `None` | 设置配置项（运行时） |
| `has` | `key: str` | `bool` | 检查配置项是否存在 |
| `as_dict` | 无 | `dict` | 返回完整配置字典 |
| `to_yaml` | 无 | `str` | 导出为YAML字符串 |
| `to_json` | 无 | `str` | 导出为JSON字符串 |

**数据模型**：

| 模型 | 字段 | 说明 |
|------|------|------|
| `DatabaseConfig` | type, host, port, name, user, password, pool, ssl | 数据库配置 |
| `LLMConfig` | provider, model, api_key_env, timeout, max_retries, rate_limit, fallback | LLM配置 |
| `VectorConfig` | type, host, port, dimension, index | 向量存储配置 |
| `CacheConfig` | type, host, port, password, db, pool | 缓存配置 |

**使用示例**：

```python
# 支持点号路径访问嵌套配置
host = config.get("database.host")
pool_size = config.get("database.pool.max_size", default=10)

# 批量获取配置项
db_config = config.get("database")
print(db_config["host"], db_config["port"])

# 检查配置项是否存在
if config.has("llm.fallback.enabled"):
    fallback_chain = config.get("llm.fallback_chain")
```

---

### ConfigSource 接口（扩展点）

**位置**：`infra/config/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `load` | 无 | `dict` | 加载配置字典 |
| `watch` | `callback: Callable` | `None` | 监听配置变更（可选） |
| `priority` | 无 | `int` | 配置源优先级（0-100） |

**基类实现**：`ConfigSource` 位于 `infra/config/sources/base.py`，提供通用方法和监听器支持

**内置实现**：

| 实现类 | 说明 | 优先级 |
|--------|------|--------|
| `FileSource` | YAML/JSON文件配置源 | 0（默认）、75（环境） |
| `EnvSource` | 环境变量配置源 | 100（最高） |

**扩展实现**（示例）：

| 实现类 | 说明 | 优先级 |
|--------|------|--------|
| `ConsulSource` | Consul配置中心源 | 80 |
| `EtcdSource` | etcd配置中心源 | 80 |
| `ApolloSource` | Apollo配置中心源 | 80 |

---

## 🏭 工厂函数

### create_config_loader

**位置**：`infra/config/factory.py`

**函数签名**：

```python
def create_config_loader(
    config: Optional[ConfigLoaderConfig] = None
) -> ConfigLoader:
    """
    创建配置加载器

    参数：
        config: 加载器配置（可选）
            - sources: 配置源列表
            - watch_enabled: 是否启用监听
            - reload_interval: 自动重载间隔（秒）
            - validate: 是否启用校验

    返回：
        ConfigLoader 实例
    """
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sources` | List[ConfigSource] | [FileSource, EnvSource] | 配置源列表 |
| `watch_enabled` | bool | True | 是否启用配置监听 |
| `reload_interval` | int | 60 | 自动重载间隔（秒） |
| `validate` | bool | True | 是否启用配置校验 |

**使用示例**：

```python
from infra.config import create_config_loader, FileSource, EnvSource

# 方式1：使用默认配置
loader = create_config_loader()
config = loader.load("config/infra/development.yaml")

# 方式2：自定义配置源
from infra.config.sources import ConsulSource

loader = create_config_loader(ConfigLoaderConfig(
    sources=[
        FileSource("config/infra/default.yaml", priority=0),
        FileSource("config/infra/production.yaml", priority=75),
        EnvSource(priority=100),
        ConsulSource(url="http://consul:8500", token="xxx", priority=80)
    ],
    watch_enabled=True,
    reload_interval=300,
    validate=True
))

config = loader.load()
```

---

## 📊 配置优先级

配置加载优先级（从低到高）：

```
1. 默认配置文件 (priority=0)
   config/infra/default.yaml

2. 环境配置文件 (priority=75)
   config/infra/development.yaml
   config/infra/production.yaml

3. 配置中心 (priority=80) [扩展]
   Consul / etcd / Apollo

4. 环境变量 (priority=100)
   export INFRA_LLM_MODEL=gpt-4-turbo
   export INFRA_DATABASE_HOST=prod-db.example.com
```

**优先级合并示例**：

```yaml
# default.yaml (priority=0)
database:
  host: localhost
  port: 5432
  pool:
    max_size: 20

# production.yaml (priority=75)
database:
  host: prod-db.example.com
  pool:
    max_size: 100

# 环境变量 (priority=100)
export DB_PORT=5433

# 最终合并结果：
database:
  host: prod-db.example.com      # 来自production.yaml
  port: 5433                      # 来自环境变量
  pool:
    max_size: 100                 # 来自production.yaml
```

---

## 🔔 配置变更通知

### 监听配置变更

**函数签名**：

```python
def on_config_change(
    callback: Callable[[List[str], Config], None]
) -> None:
    """
    注册配置变更回调

    参数：
        callback: 回调函数
            - changed_keys: 变更的配置键列表
            - new_config: 新的配置对象

    示例：
        def handle_change(changed_keys, new_config):
            if "llm.model" in changed_keys:
                reload_llm_client()
        
        on_config_change(handle_change)
    """
```

**使用示例**：

```python
from infra.config import load_config, on_config_change

def handle_config_change(changed_keys: list, new_config: Config):
    """配置变更回调"""
    
    # LLM模型变更
    if "llm.model" in changed_keys:
        logger.info(f"LLM model changed to {new_config.get('llm.model')}")
        reload_llm_client()
    
    # 数据库连接池变更
    if "database.pool.max_size" in changed_keys:
        logger.info(f"Pool size changed to {new_config.get('database.pool.max_size')}")
        resize_connection_pool()
    
    # Redis配置变更
    if "cache.host" in changed_keys or "cache.port" in changed_keys:
        logger.info("Redis config changed, reconnecting...")
        reconnect_redis()

# 注册回调
on_config_change(handle_config_change)

# 加载配置（自动启动监听）
config = load_config("config/infra/development.yaml", watch=True)
```

### 动态重载

```python
from infra.config import reload_config, reload_config_async

# 同步重载配置
new_config = reload_config()

# 异步重载配置（推荐）
new_config = await reload_config_async()

# 重载特定配置项
new_config = reload_config(keys=["llm.model", "database.pool.max_size"])

# 重载并通知监听器
reload_config(notify=True)
```

### 取消监听

```python
from infra.config import off_config_change

# 取消监听
off_config_change(handle_config_change)

# 取消所有监听
off_config_change(all=True)
```

---

## ✅ 配置校验

### 内置校验规则

| 配置项 | 校验规则 | 错误类型 | 错误信息 |
|--------|----------|----------|----------|
| `database.host` | 非空字符串 | `ConfigValidationError` | database.host is required |
| `database.port` | 1-65535 整数 | `ConfigValidationError` | database.port must be 1-65535 |
| `database.pool.max_size` | >= `pool.min_size` | `ConfigValidationError` | pool.max_size must >= pool.min_size |
| `database.pool.min_size` | > 0 整数 | `ConfigValidationError` | pool.min_size must > 0 |
| `llm.timeout` | > 0 整数 | `ConfigValidationError` | llm.timeout must > 0 |
| `llm.max_retries` | 1-10 整数 | `ConfigValidationError` | llm.max_retries must be 1-10 |
| `llm.rate_limit.max_concurrent` | > 0 整数 | `ConfigValidationError` | rate_limit.max_concurrent must > 0 |
| `vector.dimension` | > 0 整数 | `ConfigValidationError` | vector.dimension must > 0 |
| `cache.port` | 1-65535 整数 | `ConfigValidationError` | cache.port must be 1-65535 |

### 自定义校验

```python
from infra.config import validate, ConfigValidationError

@validate("database")
def validate_database_config(config: dict):
    """校验数据库配置"""
    
    # 连接池大小校验
    pool = config.get("pool", {})
    max_size = pool.get("max_size", 20)
    min_size = pool.get("min_size", 5)
    
    if max_size < min_size:
        raise ConfigValidationError(
            f"database.pool.max_size ({max_size}) must >= "
            f"database.pool.min_size ({min_size})"
        )
    
    # 超时校验
    timeout = pool.get("pool_timeout", 30)
    if timeout > 3600:
        raise ConfigValidationError(
            f"database.pool_timeout ({timeout}) must <= 3600 seconds"
        )


@validate("llm")
def validate_llm_config(config: dict):
    """校验LLM配置"""
    
    # API密钥环境变量必须存在
    api_key_env = config.get("api_key_env")
    if not api_key_env:
        raise ConfigValidationError(
            "llm.api_key_env is required"
        )
    
    # 超时校验
    timeout = config.get("timeout", 30)
    if timeout < 1:
        raise ConfigValidationError(
            f"llm.timeout ({timeout}) must >= 1 second"
        )
    
    # 重试次数校验
    max_retries = config.get("max_retries", 3)
    if not (1 <= max_retries <= 10):
        raise ConfigValidationError(
            f"llm.max_retries ({max_retries}) must be 1-10"
        )
    
    # 降级链校验
    fallback = config.get("fallback", {})
    if fallback.get("enabled"):
        chain = fallback.get("fallback_chain", [])
        if len(chain) == 0:
            raise ConfigValidationError(
                "llm.fallback.fallback_chain must have at least one model"
            )


@validate("cache")
def validate_cache_config(config: dict):
    """校验缓存配置"""
    
    if config.get("type") == "redis":
        # Redis必须配置host
        if not config.get("host"):
            raise ConfigValidationError("cache.host is required for redis")
        
        # Redis端口范围
        port = config.get("port", 6379)
        if not (1 <= port <= 65535):
            raise ConfigValidationError(f"cache.port ({port}) must be 1-65535")
        
        # Redis数据库编号范围
        db = config.get("db", 0)
        if not (0 <= db <= 15):
            raise ConfigValidationError(f"cache.db ({db}) must be 0-15")
```

### 校验错误处理

```python
from infra.config import load_config, ConfigValidationError

try:
    # 加载配置（自动校验）
    config = load_config("config/infra/development.yaml", validate=True)
except ConfigValidationError as e:
    logger.error(f"配置校验失败: {e}")
    print(f"错误配置项: {e.key}")
    print(f"错误值: {e.value}")
    print(f"错误原因: {e.reason}")
    sys.exit(1)

# 跳过校验（不推荐）
config = load_config("config/infra/development.yaml", validate=False)
```

---

## 🔧 扩展指南

### 添加新的配置源（Consul示例）

#### 步骤1：实现ConfigSource接口

**文件**：`infra/config/sources/consul.py`

```python
from infra.config.sources.base import ConfigSource
from typing import Callable, Dict, Optional
import json

class ConsulSource(ConfigSource):
    """Consul配置中心源"""
    
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        path: str = "infra/config",
        priority: int = 80
    ):
        """
        初始化Consul配置源
        
        参数：
            url: Consul服务器地址
            token: ACL令牌（可选）
            path: 配置路径
            priority: 优先级（默认80）
        """
        self.url = url
        self.token = token
        self.path = path
        self.priority = priority
        self._client = None
    
    def _get_client(self):
        """获取Consul客户端（延迟初始化）"""
        if self._client is None:
            try:
                import consul
                self._client = consul.Consul(
                    host=self.url.split("://")[1].split(":")[0],
                    port=int(self.url.split(":")[-1].split("/")[0]),
                    token=self.token
                )
            except ImportError:
                raise ImportError(
                    "consul package is required for ConsulSource. "
                    "Install it with: pip install python-consul"
                )
        return self._client
    
    def load(self) -> Dict:
        """从Consul加载配置"""
        client = self._get_client()
        index, data = client.kv.get(self.path, recurse=True)
        
        config = {}
        if data:
            for item in data:
                # 转换路径为配置键
                key = item['Key'].replace(self.path + '/', '').replace('/', '.')
                value = item['Value']
                if value:
                    try:
                        config[key] = json.loads(value.decode('utf-8'))
                    except json.JSONDecodeError:
                        config[key] = value.decode('utf-8')
        
        return config
    
    def watch(self, callback: Callable[[Dict], None]) -> None:
        """监听Consul配置变更"""
        client = self._get_client()
        
        def _watch_loop():
            index = None
            while True:
                try:
                    # Consul阻塞查询
                    index, data = client.kv.get(
                        self.path,
                        index=index,
                        recurse=True
                    )
                    if data:
                        new_config = self._parse_data(data)
                        callback(new_config)
                except Exception as e:
                    logger.error(f"Consul watch error: {e}")
                    time.sleep(5)  # 错误重试
        
        import threading
        thread = threading.Thread(target=_watch_loop, daemon=True)
        thread.start()
```

#### 步骤2：注册到工厂

**文件**：`infra/config/factory.py`

```python
from infra.config.sources import FileSource, EnvSource
from infra.config.sources.consul_source import ConsulSource

def create_config_loader(config: ConfigLoaderConfig) -> ConfigLoader:
    """创建配置加载器"""
    sources = []
    
    # 文件源
    if config.file and config.file.enabled:
        sources.append(FileSource(
            path=config.file.path,
            priority=config.file.priority
        ))
    
    # 环境变量源
    if config.env and config.env.enabled:
        sources.append(EnvSource(priority=config.env.priority))
    
    # Consul源（扩展）
    if config.consul and config.consul.enabled:
        sources.append(ConsulSource(
            url=config.consul.url,
            token=config.consul.token,
            path=config.consul.path,
            priority=config.consul.priority
        ))
    
    return ConfigLoader(
        sources=sources,
        watch_enabled=config.watch_enabled,
        reload_interval=config.reload_interval,
        validate=config.validate
    )
```

#### 步骤3：添加配置

**文件**：`config/infra/development.yaml`

```yaml
# 配置源配置
config_sources:
  file:
    enabled: true
    path: config/infra/default.yaml
    priority: 0
  
  env:
    enabled: true
    priority: 100
  
  # Consul配置中心（扩展）
  consul:
    enabled: true
    url: http://consul.example.com:8500
    token: ${CONSUL_TOKEN}
    path: infra/config
    priority: 80
    watch: true
```

---

### 添加新校验规则

#### 步骤1：定义校验函数

**文件**：`infra/config/validators.py`

```python
from infra.config import validate, ConfigValidationError

@validate("redis")
def validate_redis_config(config: dict):
    """校验Redis配置"""
    
    if config.get("type") == "redis":
        # 必须配置host
        if not config.get("host"):
            raise ConfigValidationError(
                "cache.host is required for redis"
            )
        
        # 端口范围
        port = config.get("port", 6379)
        if not (1 <= port <= 65535):
            raise ConfigValidationError(
                f"cache.port ({port}) must be 1-65535"
            )
        
        # 数据库编号范围
        db = config.get("db", 0)
        if not (0 <= db <= 15):
            raise ConfigValidationError(
                f"cache.db ({db}) must be 0-15"
            )
        
        # 连接池大小
        pool = config.get("pool", {})
        max_conn = pool.get("max_connections", 50)
        if max_conn < 1:
            raise ConfigValidationError(
                f"cache.pool.max_connections ({max_conn}) must >= 1"
            )


@validate("vector")
def validate_vector_config(config: dict):
    """校验向量存储配置"""
    
    # 向量维度必须>0
    dimension = config.get("dimension", 1536)
    if dimension <= 0:
        raise ConfigValidationError(
            f"vector.dimension ({dimension}) must > 0"
        )
    
    # 索引类型校验
    index_type = config.get("index", {}).get("type", "HNSW")
    valid_types = ["HNSW", "IVF_FLAT", "IVF_SQ8", "ANNOY"]
    if index_type not in valid_types:
        raise ConfigValidationError(
            f"vector.index.type ({index_type}) must be one of {valid_types}"
        )
```

#### 步骤2：注册校验器

校验函数通过`@validate`装饰器自动注册，无需手动注册。

加载配置时会自动调用对应命名空间的校验函数：

```python
# 加载配置时自动校验
config = load_config("config/infra/development.yaml")

# 校验顺序：
# 1. validate("database") -> validate_database_config()
# 2. validate("llm") -> validate_llm_config()
# 3. validate("cache") -> validate_cache_config()
# 4. validate("redis") -> validate_redis_config()  # 自动注册
# 5. validate("vector") -> validate_vector_config()  # 自动注册
```

---

## 🚀 使用示例

### 加载配置

```python
from infra.config import load_config

# 加载配置（自动合并默认配置、环境配置、环境变量）
config = load_config("config/infra/development.yaml")

# 获取配置项
database_host = config.get("database.host")
llm_model = config.get("llm.model")

# 获取嵌套配置
llm_config = config.get("llm")
model = llm_config["model"]
timeout = llm_config["timeout"]
```

### 环境变量覆盖

```bash
# 设置环境变量（会覆盖配置文件）
export ENV=production
export DB_HOST=prod-db.example.com
export OPENAI_API_KEY=sk-production-key
export INFRA_LLM_MODEL=gpt-4-turbo  # 覆盖模型

# Python自动读取
from infra.config import load_config
config = load_config()
model = config.get("llm.model")  # gpt-4-turbo (从环境变量)
```

---

## 📁 文件结构

```
infra/config/
├── __init__.py                  # 模块导出，提供 load_config, create_config_loader
├── loader.py                   # ConfigLoader 接口和实现（核心加载逻辑）
├── config.py                   # Config 对象（配置读取接口）
├── factory.py                  # create_config_loader() 工厂函数
├── schemas.py                  # 数据模型（DatabaseConfig, LLMConfig, VectorConfig等）
└── sources/
    ├── __init__.py
    ├── base.py                # ConfigSource 接口（扩展点）
    ├── file_source.py         # FileSource 实现（YAML/JSON文件）
    └── env_source.py          # EnvSource 实现（环境变量）

config/infra/
├── default.yaml                # 默认配置文件
├── development.yaml           # 开发环境配置
└── production.yaml          # 生产环境配置
```

**文件说明**：

| 文件 | 职责 |
|------|------|
| `loader.py` | ConfigLoader 接口定义和实现 |
| `config.py` | Config 对象，配置读取接口 |
| `factory.py` | create_config_loader() 工厂函数 |
| `schemas.py` | 数据模型定义 |
| `sources/base.py` | ConfigSource 抽象基类，扩展点 |
| `sources/file_source.py` | 文件配置源实现 |
| `sources/env_source.py` | 环境变量配置源实现 |

---

*最后更新: 2026-04-11*
