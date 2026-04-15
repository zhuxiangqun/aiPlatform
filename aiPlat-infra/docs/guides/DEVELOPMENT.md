# 基础设施层开发规范

> 继承系统级开发规范，针对基础设施层的特定要求

---

## 📋 目录

- [继承规范](#继承规范)
- [特定规范](#特定规范)
- [接口设计](#接口设计)
- [配置驱动](#配置驱动)
- [错误处理](#错误处理)
- [测试规范](#测试规范)

---

## 继承规范

本文档继承 [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)，所有系统级规范在本层必须遵守：

- **代码规范**：Python 类型注解、命名规范
- **提交规范**：Conventional Commits
- **分支策略**：Git Flow
- **PR 流程**：代码审查、CI 检查
- **测试规范**：测试金字塔、覆盖率要求

本层额外规范如下：

---

## 特定规范

### 层级定位

基础设施层是最低层，**不依赖任何内部模块**：

```
aiPlat-infra (Layer 0)
    ↓ 不依赖
    其他层可依赖
```

**禁止的依赖**：
- ❌ 禁止导入 `aiPlat_core`
- ❌ 禁止导入 `aiPlat_platform`
- ❌ 禁止导入 `aiPlat_app`

**允许的依赖**：
- ✅ Python 标准库
- ✅ 第三方库（asyncpg, redis, pydantic 等）
- ✅ 内部工具模块（logger, utils）

---

## 接口设计

### 接口定义规范

**必须定义接口**（抽象基类）：

```python
# infra/database/base.py
from abc import ABC, abstractmethod
from typing import Any

class DatabaseClient(ABC):
    """数据库客户端接口"""
    
    @abstractmethod
    async def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行查询"""
        ...
    
    @abstractmethod
    async def insert(self, table: str, data: dict[str, Any]) -> int:
        """插入数据"""
        ...
    
    @abstractmethod
    async def update(self, table: str, data: dict[str, Any], where: dict[str, Any]) -> int:
        """更新数据"""
        ...
    
    @abstractmethod
    async def delete(self, table: str, where: dict[str, Any]) -> int:
        """删除数据"""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        ...
```

### 实现类命名

```python
# infra/database/postgres.py
from .base import DatabaseClient

class PostgresClient(DatabaseClient):
    """PostgreSQL 实现"""
    
    def __init__(self, config: PostgresConfig):
        self._config = config
        self._pool: asyncpg.Pool | None = None
    
    async def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # 具体实现
        ...
```

### 工厂函数

**统一入口**：通过工厂函数创建实例，不直接实例化实现类：

```python
# infra/factories/database.py
from typing import Literal
from ..database.base import DatabaseClient
from ..database.postgres import PostgresClient
from ..database.mysql import MySQLClient
from ..database.mongodb import MongoClient

def create_database_client(
    backend: Literal["postgres", "mysql", "mongodb", "sqlite"],
    config: dict[str, Any]
) -> DatabaseClient:
    """
    创建数据库客户端
    
    Args:
        backend: 数据库类型
        config: 配置字典
    
    Returns:
        DatabaseClient 实例
    
    Example:
        >>> client = create_database_client("postgres", {"host": "localhost", ...})
    """
    match backend:
        case "postgres":
            return PostgresClient(PostgresConfig(**config))
        case "mysql":
            return MySQLClient(MySQLConfig(**config))
        case "mongodb":
            return MongoClient(MongoConfig(**config))
        case "sqlite":
            return SQLiteClient(SQLiteConfig(**config))
        case _:
            raise ValueError(f"Unsupported backend: {backend}")
```

---

## 配置驱动

### 配置结构

**必须使用配置对象**（Pydantic BaseModel）：

```python
# infra/database/config.py
from pydantic import BaseModel, Field

class PostgresConfig(BaseModel):
    """PostgreSQL 配置"""
    
    host: str = Field(..., description="数据库主机")
    port: int = Field(5432, description="端口")
    database: str = Field(..., description="数据库名")
    user: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    
    # 连接池配置
    min_connections: int = Field(5, ge=1, description="最小连接数")
    max_connections: int = Field(20, ge=1, description="最大连接数")
    connection_timeout: float = Field(60.0, gt=0, description="连接超时(秒)")
    
    class Config:
        # 支持环境变量
        env_prefix = "DATABASE_POSTGRES_"
```

**禁止硬编码**：

```python
# ❌ 禁止
client = PostgresClient(
    host="localhost",
    port=5432,
    user="postgres",
    password="hardcoded_password"  # 安全风险！
)

# ✅ 正确
config = load_config("config/infra/database.yaml")
client = create_database_client("postgres", config.postgres)
```

### 配置加载

```python
# infra/config/loader.py
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel

def load_config(config_path: str | Path) -> dict[str, Any]:
    """
    加载配置文件
    
    支持：
    - YAML 文件
    - 环境变量覆盖
    - 多环境配置
    
    Example:
        >>> config = load_config("config/infra/database.yaml")
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path) as f:
        config = yaml.safe_load(f)
    
    # 环境变量覆盖
    config = _apply_env_overrides(config)
    
    return config
```

---

## 错误处理

### 异常层次

**定义层级别异常**：

```python
# infra/exceptions.py
from typing import Any

class InfraError(Exception):
    """基础设施层基础异常"""
    pass

class InfraConnectionError(InfraError):
    """连接错误"""
    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(f"{service} connection error: {message}")

class InfraTimeoutError(InfraError):
    """超时错误"""
    def __init__(self, service: str, timeout: float):
        self.service = service
        self.timeout = timeout
        super().__init__(f"{service} timeout after {timeout}s")

class InfraConfigError(InfraError):
    """配置错误"""
    def __init__(self, message: str, config_key: str | None = None):
        self.config_key = config_key
        super().__init__(message)

class InfraOperationError(InfraError):
    """操作错误"""
    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"{operation} failed: {message}")
```

### 错误处理最佳实践

```python
# ✅ 正确：捕获具体异常，转换为层级别异常
async def query_with_retry(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *params.values())
    except asyncpg.PostgresConnectionError as e:
        raise InfraConnectionError("postgres", str(e))
    except asyncio.TimeoutError as e:
        raise InfraTimeoutError("postgres", self._config.connection_timeout)

# ❌ 禁止：暴露底层异常
async def query_bad(self, sql: str) -> list:
    result = await self._conn.fetch(sql)
    return result  # 如果失败，暴露 asyncpg 异常到上层
```

---

## 测试规范

继承系统级测试规范，详见 [测试指南](../testing/TESTING_GUIDE.md)。

### 测试覆盖率要求

| 模块 | 单元测试 | 集成测试 | 总覆盖率 |
|------|----------|----------|----------|
| 数据库 | ≥ 80% | ≥ 70% | ≥ 85% |
| LLM | ≥ 80% | Mock | ≥ 80% |
| 向量存储 | ≥ 80% | Mock | ≥ 80% |
| 消息队列 | ≥ 80% | ≥ 70% | ≥ 85% |

### 测试组织

```
aiPlat-infra/
└── infra/tests/
    ├── unit/                    # 单元测试
    │   ├── test_database.py
    │   ├── test_llm.py
    │   └── test_vector.py
    │
    ├── integration/             # 集成测试
    │   ├── test_postgres_integration.py
    │   └── test_mysql_integration.py
    │
    └── conftest.py              # 测试配置
```

### 单元测试示例

```python
# tests/unit/test_database.py
import pytest
from infra.database.postgres import PostgresClient
from infra.database.config import PostgresConfig

def test_postgres_config_validation():
    """测试配置验证"""
    # 有效配置
    config = PostgresConfig(host="localhost", database="test")
    assert config.port == 5432  # 默认值
    
    # 无效配置
    with pytest.raises(ValueError):
        PostgresConfig(host="")  # 空主机名

def test_postgres_client_build_query():
    """测试查询构建"""
    client = PostgresClient(PostgresConfig(host="localhost", database="test"))
    query, params = client._build_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": 1}
    )
    assert "SELECT" in query
    assert params == (1,)
```

### 集成测试示例

```python
# tests/integration/test_postgres_integration.py
import pytest
from testcontainers.postgres import PostgresContainer
from infra.database.postgres import PostgresClient
from infra.database.config import PostgresConfig

@pytest.fixture
async def postgres_container():
    """启动 PostgreSQL 容器"""
    container = PostgresContainer("postgres:15")
    container.start()
    yield container
    container.stop()

@pytest.fixture
async def db_client(postgres_container):
    """创建数据库客户端"""
    config = PostgresConfig(
        host=postgres_container.get_container_host_ip(),
        port=postgres_container.get_exposed_port(5432),
        database=postgres_container.POSTGRES_DB,
        user=postgres_container.POSTGRES_USER,
        password=postgres_container.POSTGRES_PASSWORD
    )
    client = PostgresClient(config)
    await client.connect()
    yield client
    await client.close()

async def test_postgres_crud(db_client):
    """测试 CRUD 操作"""
    # Create
    await db_client.insert("users", {"name": "test", "email": "test@example.com"})
    
    # Read
    users = await db_client.query("SELECT * FROM users WHERE name = :name", {"name": "test"})
    assert len(users) == 1
    
    # Update
    await db_client.update("users", {"name": "updated"}, {"name": "test"})
    
    # Delete
    await db_client.delete("users", {"name": "updated"})
```

---

## 模块开发指南

### 添加新数据库支持

1. **定义接口**：确保实现 `DatabaseClient` 接口
2. **创建配置**：继承 Pydantic BaseModel
3. **实现类**：继承 `DatabaseClient`
4. **工厂注册**：在 `create_database_client` 中添加新 backend
5. **编写测试**：单元测试 + 集成测试
6. **更新文档**：在模块文档中添加使用示例

### 添加新 LLM 提供商

1. **继承接口**：实现 `LLMClient` 接口
2. **配置类**：创建 `<Provider>Config`
3. **工厂注册**：在 `create_llm_client` 中添加新 provider
4. **编写测试**：使用 Mock 测试（不需要真实 API）
5. **错误处理**：转换为 `InfraError` 层级异常

---

## 代码审查检查清单

### 必须检查

- [ ] 是否定义了接口（Abstract Base Class）
- [ ] 是否使用配置对象（不硬编码）
- [ ] 是否使用工厂函数（不直接实例化）
- [ ] 是否正确处理异常（转换为层级别异常）
- [ ] 是否有单元测试
- [ ] 是否有集成测试（如适用）
- [ ] 是否有类型注解
- [ ] 是否有文档字符串

---

## 相关链接

- [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)
- [infra层测试指南](../testing/TESTING_GUIDE.md)
- [infra层部署指南](./DEPLOYMENT.md)

---

*最后更新: 2026-04-11*