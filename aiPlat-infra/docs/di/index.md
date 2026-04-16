# 依赖注入模块（设计真值：以代码事实为准）

> 说明：本文档描述 infra 内置 DI 容器的 As-Is 实现与可配置项。  
> 关键断言需可追溯（代码入口/测试/命令），并与全仓口径保持一致。

> 提供轻量级依赖注入容器，用于 infra 层内部模块之间的依赖管理

---

## 🎯 模块定位

依赖注入模块负责管理 infra 层内部模块的依赖关系，支持：
- 服务注册
- 依赖解析
- 生命周期管理
- 作用域控制
- 延迟初始化

> **注意**：此 DI 容器用于 infra 内部模块之间的依赖管理。与框架级 DI（如 FastAPI）不冲突：infra 内部使用自带的 DI 容器，上层通过工厂接口获取 infra 实例。

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
di:
  # 容器配置
  container:
    auto_wire: true              # 自动注入
    scan_packages:              # 扫描包
      - infra.database
      - infra.llm
      - infra.vector
    strict_mode: false          # 严格模式
  
  # 服务生命周期
  lifecycle:
    singleton: true             # 默认单例
    lazy_init: true             # 延迟初始化
  
  # 作用域
  scopes:
    - name: global
      lifecycle: singleton
    - name: request
      lifecycle: transient
    - name: session
      lifecycle: scoped
  
  # 拦截器
  interceptors:
    - logging
    - metrics
    - error_handling
```

---

## 📖 核心接口定义

### DIContainer 接口

**位置**：`infra/di/container.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `register` | `service: Type`, `impl: Type`, `scope: str` | `None` | 注册服务 |
| `register_instance` | `service: Type`, `instance: Any` | `None` | 注册实例 |
| `register_factory` | `service: Type`, `factory: Callable` | `None` | 注册工厂 |
| `resolve` | `service: Type` | `Any` | 解析服务 |
| `resolve_all` | `service: Type` | `List[Any]` | 解析所有实现 |
| `create_scope` | `scope: str` | `IScope` | 创建作用域 |

### IScope 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `resolve` | `service: Type` | `Any` | 作用域内解析 |
| `close` | 无 | `None` | 关闭作用域 |

---

## 🏭 工厂函数

### create_container

**位置**：`infra/di/factory.py`

**函数签名**：

```python
def create_container(
    config: Optional[DIContainerConfig] = None
) -> DIContainer:
    """
    创建 DI 容器

    参数：
        config: 容器配置（可选）

    返回：
        DIContainer 实例
    """
```

**使用示例**：

```python
from infra.di import create_container

# 创建容器
container = create_container()

# 注册服务
container.register(IDatabaseClient, PostgresClient)
container.register(ILLMClient, OpenAIClient)
container.register(IVectorStore, MilvusStore)

# 解析服务
db = container.resolve(IDatabaseClient)
llm = container.resolve(ILLMClient)

# 使用作用域
with container.scope("request") as scope:
    db = scope.resolve(IDatabaseClient)
    # 请求结束时自动清理
```

---

## 📊 数据模型

### DIContainerConfig

```python
@dataclass
class DIContainerConfig:
    auto_wire: bool = True
    scan_packages: List[str] = field(default_factory=list)
    strict_mode: bool = False
    default_singleton: bool = True
    default_lazy: bool = True
    interceptors: List[str] = field(default_factory=list)
```

### ServiceDescriptor

```python
@dataclass
class ServiceDescriptor:
    service: Type
    implementation: Type
    scope: str = "global"
    lifetime: Lifetime = Lifetime.SINGLETON
    factory: Optional[Callable] = None
    instance: Optional[Any] = None

class Lifetime(Enum):
    TRANSIENT = "transient"     # 每次请求新实例
    SCOPED = "scoped"           # 作用域内单例
    SINGLETON = "singleton"      # 全局单例
```

---

## 🚀 使用示例

### 基本使用

```python
from infra.di import create_container, injectable

# 创建容器
container = create_container()

# 方式1：装饰器注册
@injectable
class DatabaseService:
    def __init__(self, config: DatabaseConfig):
        self.config = config
    
    async def query(self, sql: str):
        pass

# 方式2：手动注册
container.register(IDatabaseClient, PostgresClient)

# 方式3：实例注册
db_client = PostgresClient(config)
container.register_instance(IDatabaseClient, db_client)

# 方式4：工厂注册
def create_db():
    return PostgresClient(config)
container.register_factory(IDatabaseClient, create_db)

# 解析
db = container.resolve(IDatabaseClient)
```

### 自动注入

```python
from infra.di import injectable

# 定义服务
@injectable
class UserRepository:
    def __init__(self, db: IDatabaseClient):
        self.db = db
    
    async def get_user(self, user_id: str):
        return await self.db.query(
            "SELECT * FROM users WHERE id = :id",
            {"id": user_id}
        )

# 定义依赖链
@injectable
class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository
    
    async def get_user(self, user_id: str):
        return await self.repository.get_user(user_id)

# 自动解析
service = container.resolve(UserService)
```

### 作用域管理

```python
# 全局单例
container.register(ILogger, LoggerService)

# 请求作用域
with container.create_scope("request") as scope:
    # 每个请求一个实例
    user_service = scope.resolve(UserService)
    
    # 同一作用域内多次解析返回同一实例
    user_service2 = scope.resolve(UserService)
    assert user_service is user_service2

# 会话作用域
with container.create_scope("session") as scope:
    session_db = scope.resolve(SessionDatabase)
    # 会话结束自动清理
```

### 拦截器

```python
from infra.di import Interceptor

class LoggingInterceptor(Interceptor):
    """日志拦截器"""
    
    def intercept(self, invocation: Invocation):
        logger.info(f"Calling {invocation.method.name}")
        start = time.time()
        result = invocation.proceed()
        logger.info(f"Completed in {time.time() - start:.3f}s")
        return result

class MetricsInterceptor(Interceptor):
    """指标拦截器"""
    
    def intercept(self, invocation: Invocation):
        metric = f"infra.{invocation.method.declaring_class.__name__}.{invocation.method.name}"
        metrics.counter(metric).inc()
        return invocation.proceed()

# 注册拦截器
container.interceptors.add(LoggingInterceptor())
container.interceptors.add(MetricsInterceptor())
```

---

## 🔧 扩展指南

### 添加新的生命周期

```python
from infra.di import Lifetime

class CustomLifetime(Lifetime):
    """自定义生命周期"""
    THREAD_LOCAL = "thread_local"  # 线程本地单例

# 使用
container.register(
    IThreadService,
    ThreadService,
    lifetime=CustomLifetime.THREAD_LOCAL
)
```

> 说明（As-Is）：当前仓库已提供 `@injectable` 与 scan_packages 自动注册；`inject` 装饰器若需要，应作为 To-Be 补齐实现与测试（避免文档宣称超前）。

---

## 证据索引（Evidence Index｜抽样）

- DIContainerConfig（含 interceptors）：`infra/di/schemas.py`
- scan_packages 导入 + @injectable 自动注册：`infra/di/container.py`、`infra/di/auto.py`
- 拦截器链与 Proxy：`infra/di/interceptors.py`
- 单测：`infra/tests/unit/test_di_scan_and_interceptors.py`

### 添加新的作用域

```python
from infra.di import IScope

class TenantScope(IScope):
    """租户作用域"""
    
    def __init__(self, container: DIContainer, tenant_id: str):
        self.container = container
        self.tenant_id = tenant_id
        self._cache = {}
    
    def resolve(self, service: Type):
        key = f"{self.tenant_id}:{service.__name__}"
        if key not in self._cache:
            self._cache[key] = self.container._create_instance(service)
        return self._cache[key]
    
    def close(self):
        # 清理租户资源
        pass

# 使用
with container.create_tenant_scope("tenant-123") as scope:
    service = scope.resolve(ITenantService)
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `di.container.auto_wire` | 布尔值 | must be boolean |
| `di.lifecycle.singleton` | 布尔值 | must be boolean |
| `di.lifecycle.lazy_init` | 布尔值 | must be boolean |
| `di.strict_mode` | 布尔值 | must be boolean |

---

## 📁 文件结构

```
infra/di/
├── __init__.py                  # 模块导出
├── base.py                     # DIContainer 接口
├── container.py                # DIContainer 实现
├── factory.py                  # create_container()
├── schemas.py                  # 数据模型
├── scopes.py                   # 作用域管理
├── interceptors.py             # 拦截器
├── resolvers.py                # 依赖解析器
└── registries.py              # 服务注册表
```

---

*最后更新: 2026-04-11*
