# 数据库模块（设计真值：以代码事实为准）

> 说明：数据库模块的 As-Is 能力以 `infra/database/*` 代码与测试为准；文档中的多后端/ORM/迁移等若未实现需标注为 To-Be。

> 提供数据库抽象层，支持多种数据库后端（PostgreSQL/MySQL/MongoDB）

---

## 🎯 模块定位

数据库模块负责统一管理所有数据库连接和操作，支持：
- 多数据库后端（PostgreSQL/MySQL/MongoDB）
- 连接池管理
- 事务支持
- ORM/非ORM模式
- 连接池监控

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
database:
  type: postgres                    # postgres, mysql, mongodb
  host: localhost
  port: 5432
  name: ai_platform
  user: ${DB_USER}
  password: ${DB_PASSWORD}
  
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
  
  # 超时配置
  connect_timeout: 10
  command_timeout: 30
  
  # 延迟初始化
  lazy_init: true
```

---

## 📖 核心接口定义

### DatabaseClient 接口

**位置**：`infra/database/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute` | `query: str`, `params: dict` | `List[dict]` | 执行查询，返回结果列表 |
| `execute_one` | `query: str`, `params: dict` | `Optional[dict]` | 执行查询，返回单条结果 |
| `execute_many` | `query: str`, `params_list: List[dict]` | `List[Any]` | 批量执行 |
| `transaction` | 无 | `AsyncContextManager` | 获取事务上下文管理器 |
| `begin` | 无 | `None` | 开始事务 |
| `commit` | 无 | `None` | 提交事务 |
| `rollback` | 无 | `None` | 回滚事务 |
| `close` | 无 | `None` | 关闭连接 |
| `is_connected` | 无 | `bool` | 检查连接状态 |

**支持的后端**：
- `postgres`：PostgreSQL（推荐）
- `mysql`：MySQL
- `mongodb`：MongoDB
- `sqlite`：SQLite（开发测试用）

---

### ConnectionPool 接口

**位置**：`infra/database/pool.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `acquire` | 无 | `Connection` | 获取连接 |
| `release` | `conn: Connection` | `None` | 释放连接 |
| `get_stats` | 无 | `PoolStats` | 获取连接池统计 |
| `resize` | `min: int`, `max: int` | `None` | 调整连接池大小 |
| `close` | 无 | `None` | 关闭连接池 |

**PoolStats 数据模型**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `size` | int | 当前连接数 |
| `available` | int | 可用连接数 |
| `used` | int | 使用中连接数 |
| `overflow` | int | 溢出连接数 |
| `waiting` | int | 等待获取连接的请求数 |

---

## 🏭 工厂函数

### create_database_client

**位置**：`infra/database/factory.py`

**函数签名**：

```python
def create_database_client(config: DatabaseConfig) -> DatabaseClient:
    """
    创建数据库客户端

    参数：
        config: 数据库配置
            - type: 数据库类型
            - host: 主机地址
            - port: 端口
            - name: 数据库名
            - user: 用户名
            - password: 密码
            - pool: 连接池配置

    返回：
        DatabaseClient 实例
    """
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config.type` | str | "postgres" | 数据库类型 |
| `config.host` | str | "localhost" | 数据库主机 |
| `config.port` | int | 5432 | 数据库端口 |
| `config.name` | str | "ai_platform" | 数据库名称 |
| `config.user` | str | "postgres" | 用户名 |
| `config.password` | str | "" | 密码 |
| `config.pool.min_size` | int | 5 | 连接池最小连接数 |
| `config.pool.max_size` | int | 20 | 连接池最大连接数 |
| `config.pool.max_overflow` | int | 10 | 最大溢出连接数 |
| `config.pool.timeout` | int | 30 | 获取连接超时时间 |

**使用示例**：

```python
from infra.database import create_database_client
from infra.database.schemas import DatabaseConfig

# 从配置创建客户端
config = DatabaseConfig(
    type="postgres",
    host="localhost",
    port=5432,
    name="ai_platform",
    user="postgres",
    password="password",
    pool=PoolConfig(min_size=5, max_size=20)
)
db = create_database_client(config)

# 执行查询
result = await db.execute("SELECT * FROM users WHERE id = :id", {"id": 1})
print(result)

# 事务操作
async with db.transaction() as tx:
    await tx.execute(
        "INSERT INTO logs (message) VALUES (:message)",
        {"message": "test"}
    )
```

---

## 📊 数据模型

### DatabaseConfig

```python
@dataclass
class DatabaseConfig:
    type: str = "postgres"
    host: str = "localhost"
    port: int = 5432
    name: str = "ai_platform"
    user: str = "postgres"
    password: str = ""
    pool: Optional[PoolConfig] = None
    ssl: Optional[SSLConfig] = None
    lazy_init: bool = True
```

### PoolConfig

```python
@dataclass
class PoolConfig:
    min_size: int = 5
    max_size: int = 20
    max_overflow: int = 10
    timeout: int = 30
    recycle: int = 3600
```

### SSLConfig

```python
@dataclass
class SSLConfig:
    enabled: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    verify_mode: str = "REQUIRED"
```

---

## 🚀 使用示例

### 基本查询

```python
from infra.database import create_database_client

# 创建数据库客户端
db = create_database_client(DatabaseConfig(
    type="postgres",
    host="localhost",
    name="ai_platform"
))

# 查询单条
user = await db.execute_one(
    "SELECT * FROM users WHERE id = :id",
    {"id": 1}
)

# 查询多条
users = await db.execute(
    "SELECT * FROM users WHERE status = :status",
    {"status": "active"}
)

# 插入数据
await db.execute(
    "INSERT INTO users (name, email) VALUES (:name, :email)",
    {"name": "Alice", "email": "alice@example.com"}
)

# 更新数据
await db.execute(
    "UPDATE users SET name = :name WHERE id = :id",
    {"name": "Alice Smith", "id": 1}
)

# 删除数据
await db.execute(
    "DELETE FROM users WHERE id = :id",
    {"id": 1}
)
```

### 事务操作

```python
# 方式1：使用transaction上下文管理器
async with db.transaction() as tx:
    await tx.execute(
        "INSERT INTO accounts (id, balance) VALUES (:id, :balance)",
        {"id": 1, "balance": 1000}
    )
    await tx.execute(
        "UPDATE accounts SET balance = balance - :amount WHERE id = :id",
        {"amount": 100, "id": 1}
    )

# 方式2：手动管理事务
await db.begin()
try:
    await db.execute("INSERT INTO logs (msg) VALUES (:msg)", {"msg": "test"})
    await db.commit()
except Exception:
    await db.rollback()
    raise
```

### 连接池管理

```python
# 获取连接池统计
stats = db.pool.get_stats()
print(f"Pool size: {stats.size}, available: {stats.available}, used: {stats.used}")

# 动态调整连接池
await db.pool.resize(min_size=10, max_size=30)

# 检查连接状态
if db.is_connected():
    print("Database is connected")
```

### 批量操作

```python
# 批量插入
users = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"}
]
await db.execute_many(
    "INSERT INTO users (name, email) VALUES (:name, :email)",
    users
)

# 批量更新
updates = [
    {"id": 1, "name": "Alice Updated"},
    {"id": 2, "name": "Bob Updated"},
    {"id": 3, "name": "Charlie Updated"}
]
await db.execute_many(
    "UPDATE users SET name = :name WHERE id = :id",
    updates
)
```

---

## 🔧 扩展指南

### 添加新的数据库实现

#### 步骤1：实现DatabaseClient接口

**文件**：`infra/database/oracle.py`

```python
from infra.database.base import DatabaseClient
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

class OracleClient(DatabaseClient):
    """Oracle 数据库客户端"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._connection = None
        self._pool = None
    
    async def connect(self):
        """建立连接"""
        import oracledb
        self._connection = await oracledb.connect(
            user=self.config.user,
            password=self.config.password,
            dsn=f"{self.config.host}:{self.config.port}/{self.config.name}"
        )
    
    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        """执行查询"""
        cursor = self._connection.cursor()
        try:
            cursor.execute(query, params or {})
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()
    
    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """执行查询，返回单条"""
        results = await self.execute(query, params)
        return results[0] if results else None
    
    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        """批量执行"""
        cursor = self._connection.cursor()
        try:
            cursor.executemany(query, params_list)
            return [cursor.rowcount]
        finally:
            cursor.close()
    
    @asynccontextmanager
    async def transaction(self):
        """事务上下文"""
        tx = self._connection.transaction()
        try:
            yield tx
            await tx.commit()
        except Exception:
            await tx.rollback()
            raise
    
    async def close(self):
        """关闭连接"""
        if self._connection:
            await self._connection.close()
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connection is not None and self._connection.is_open()
```

#### 步骤2：注册到工厂

**文件**：`infra/database/factory.py`

```python
def create_database_client(config: DatabaseConfig) -> DatabaseClient:
    if config.type == "postgres":
        from infra.database.postgres import PostgresClient
        return PostgresClient(config)
    elif config.type == "mysql":
        from infra.database.mysql import MySqlClient
        return MySqlClient(config)
    elif config.type == "mongodb":
        from infra.database.mongodb import MongoClient
        return MongoClient(config)
    elif config.type == "oracle":  # 扩展示例（当前仓库未实现）
        raise NotImplementedError("oracle is not implemented in this repository")
    else:
        raise ValueError(f"Unknown database type: {config.type}")
```

#### 步骤3：添加配置

**文件**：`config/infra/development.yaml`

```yaml
database:
  type: oracle
  host: oracle.example.com
  port: 1521
  name: ai_platform
  user: ${ORACLE_USER}
  password: ${ORACLE_PASSWORD}
  
  pool:
    min_size: 5
    max_size: 20
```

---

## ✅ 配置校验

### 内置校验规则

| 配置项 | 校验规则 | 错误类型 | 错误信息 |
|--------|----------|----------|----------|
| `database.type` | 非空，在支持列表中 | `ConfigValidationError` | invalid database type |
| `database.host` | 非空字符串 | `ConfigValidationError` | database.host is required |
| `database.port` | 1-65535 整数 | `ConfigValidationError` | database.port must be 1-65535 |
| `database.name` | 非空字符串 | `ConfigValidationError` | database.name is required |
| `database.pool.max_size` | >= pool.min_size | `ConfigValidationError` | pool.max_size must >= pool.min_size |
| `database.pool.min_size` | > 0 整数 | `ConfigValidationError` | pool.min_size must > 0 |

---

## 📁 文件结构

```
infra/database/
├── __init__.py               # 模块导出
├── base.py                   # DatabaseClient 接口
├── factory.py                # create_database_client()
├── schemas.py                # 数据模型
├── pool.py                  # 连接池接口
├── postgres.py              # PostgreSQL 实现
├── mysql.py                 # MySQL 实现
├── mongodb.py               # MongoDB 实现
└── sqlite.py                # SQLite 实现
```

---

## 🔗 相关链接

- [← 返回 infra 文档索引](../index.md)
- [→ 配置管理模块](../config/index.md)
- [→ 缓存模块](../cache/index.md)

---

*最后更新: 2026-04-11*

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/database/*`
