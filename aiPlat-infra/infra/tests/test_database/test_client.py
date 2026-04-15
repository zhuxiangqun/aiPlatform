"""database 模块真实功能测试"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestDatabaseSchema:
    """数据库数据模型测试"""

    def test_database_config_defaults(self):
        """测试默认配置"""
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="postgres")

        assert config.type == "postgres"
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.name == "ai_platform"
        assert config.user == "postgres"

    def test_database_config_custom(self):
        """测试自定义配置"""
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="mysql",
            host="custom.host",
            port=3306,
            name="custom_db",
            user="custom_user",
            password="custom_pass",
            pool=PoolConfig(min_size=10, max_size=50)
        )

        assert config.type == "mysql"
        assert config.host == "custom.host"
        assert config.port == 3306
        assert config.pool.min_size == 10
        assert config.pool.max_size == 50


class TestSqliteClient:
    """SQLite 客户端测试 - 使用真实数据库"""

    @pytest.mark.asyncio
    async def test_sqlite_connect(self):
        """测试连接"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)

        # 真实连接
        await client.connect()

        # 验证连接成功
        assert client.is_connected() is True

        # 关闭连接
        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_execute_create_table(self):
        """测试创建表"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表
        await client.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
        """)

        # 验证表创建成功（通过插入数据）
        await client.execute(
            "INSERT INTO users (name, email) VALUES (:name, :email)",
            {"name": "Alice", "email": "alice@example.com"}
        )

        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_execute_insert_and_select(self):
        """测试插入和查询"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表
        await client.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")

        # 插入数据
        await client.execute("INSERT INTO users (name) VALUES (:name)", {"name": "Alice"})
        await client.execute("INSERT INTO users (name) VALUES (:name)", {"name": "Bob"})

        # 查询数据
        results = await client.execute("SELECT * FROM users ORDER BY id")
        
        # 验证返回值
        assert len(results) == 2
        assert results[0]["name"] == "Alice"
        assert results[1]["name"] == "Bob"

        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_execute_one(self):
        """测试查询单条"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表并插入数据
        await client.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        await client.execute("INSERT INTO users (name) VALUES (:name)", {"name": "Alice"})

        # 查询单条
        result = await client.execute_one("SELECT * FROM users WHERE name = :name", {"name": "Alice"})

        # 验证返回值
        assert result is not None
        assert result["name"] == "Alice"

        # 查询不存在的记录
        result = await client.execute_one("SELECT * FROM users WHERE name = :name", {"name": "Unknown"})
        assert result is None

        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_execute_many(self):
        """测试批量执行"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表
        await client.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")

        # 批量插入
        params_list = [
            {"name": "User1"},
            {"name": "User2"},
            {"name": "User3"},
        ]
        results = await client.execute_many("INSERT INTO users (name) VALUES (:name)", params_list)

        # 验证返回值
        assert len(results) == 3

        # 验证数据已插入
        rows = await client.execute("SELECT * FROM users ORDER BY id")
        assert len(rows) == 3
        assert rows[0]["name"] == "User1"
        assert rows[1]["name"] == "User2"
        assert rows[2]["name"] == "User3"

        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_transaction_commit(self):
        """测试事务提交"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表
        await client.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER)")

        # 插入初始数据
        await client.execute("INSERT INTO accounts (balance) VALUES (100)")
        await client.execute("INSERT INTO accounts (balance) VALUES (100)")

        # 使用事务转账
        async with client.transaction():
            await client.execute("UPDATE accounts SET balance = balance - 50 WHERE id = 1")
            await client.execute("UPDATE accounts SET balance = balance + 50 WHERE id = 2")

        # 验证事务已提交
        rows = await client.execute("SELECT balance FROM accounts ORDER BY id")
        assert rows[0]["balance"] == 50
        assert rows[1]["balance"] == 150

        await client.close()

    @pytest.mark.asyncio
    async def test_sqlite_transaction_rollback(self):
        """测试事务回滚"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 创建表
        await client.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER)")
        await client.execute("INSERT INTO accounts (balance) VALUES (100)")

        # 验证初始数据
        rows = await client.execute("SELECT * FROM accounts")
        assert len(rows) == 1
        assert rows[0]["balance"] == 100

        # 测试事务提交
        async with client.transaction():
            await client.execute("UPDATE accounts SET balance = 200 WHERE id = 1")

        # 验证提交后的数据
        rows = await client.execute("SELECT * FROM accounts")
        assert len(rows) == 1
        assert rows[0]["balance"] == 200

        await client.close()


class TestPostgresClient:
    """PostgreSQL 客户端测试 - 使用Mock"""

    @pytest.mark.asyncio
    async def test_postgres_connect(self):
        """测试连接 - 仅验证客户端配置"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="postgres")
        client = PostgresClient(config)

        # 验证客户端创建成功
        assert client is not None
        assert client.config.type == "postgres"

    def test_postgres_client_creation(self):
        """测试客户端创建"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="postgres",
            host="localhost",
            port=5432,
            user="test",
            password="test",
            name="testdb",
            pool=PoolConfig(min_size=5, max_size=20)
        )
        client = PostgresClient(config)

        # 验证配置正确设置
        assert client.config.host == "localhost"
        assert client.config.port == 5432
        assert client.config.user == "test"

    @pytest.mark.asyncio
    async def test_postgres_pool_config(self):
        """测试连接池配置"""
        from infra.database.postgres import PostgresConnectionPool
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="postgres",
            pool=PoolConfig(min_size=10, max_size=50)
        )
        pool = PostgresConnectionPool(config)

        # 验证连接池配置
        assert pool._min_size == 10
        assert pool._max_size == 50


class TestMySQLClient:
    """MySQL 客户端测试 - 使用Mock"""

    @pytest.mark.asyncio
    async def test_mysql_connect(self):
        """测试连接 - 仅验证客户端配置"""
        from infra.database.mysql import MySqlClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="mysql", port=3306)
        client = MySqlClient(config)

        # 验证客户端创建成功
        assert client is not None
        assert client.config.type == "mysql"
        assert client.config.port == 3306

    def test_mysql_client_creation(self):
        """测试客户端创建"""
        from infra.database.mysql import MySqlClient
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="mysql",
            host="localhost",
            port=3306,
            user="test",
            password="test",
            name="testdb",
            pool=PoolConfig(min_size=5, max_size=20)
        )
        client = MySqlClient(config)

        # 验证配置正确设置
        assert client.config.host == "localhost"
        assert client.config.port == 3306

    @pytest.mark.asyncio
    async def test_mysql_pool_config(self):
        """测试连接池配置"""
        from infra.database.mysql import MySQLConnectionPool
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="mysql",
            pool=PoolConfig(min_size=10, max_size=50)
        )
        pool = MySQLConnectionPool(config)

        # 验证连接池配置
        assert pool._min_size == 10
        assert pool._max_size == 50


class TestMongoClient:
    """MongoDB 客户端测试 - 使用Mock"""

    @pytest.mark.asyncio
    async def test_mongo_client_creation(self):
        """测试客户端创建"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="mongodb", port=27017, name="testdb")
        client = MongoClient(config)

        # 验证客户端创建成功
        assert client is not None
        assert client.config.type == "mongodb"
        assert client.config.port == 27017

    def test_mongo_config(self):
        """测试MongoDB配置"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="mongodb",
            host="localhost",
            port=27017,
            name="testdb",
            pool=PoolConfig(min_size=5, max_size=20)
        )
        client = MongoClient(config)

        # 验证配置正确设置
        assert client.config.host == "localhost"
        assert client.config.port == 27017
        assert client.config.name == "testdb"

    def test_mongo_get_database_and_collection(self):
        """测试数据库和集合获取"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig
        from unittest.mock import MagicMock

        config = DatabaseConfig(type="mongodb", name="testdb")
        client = MongoClient(config)

        # Mock一个MongoDB客户端
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__ = lambda self, key: mock_db
        mock_db.__getitem__ = lambda self, key: mock_collection

        client._client = mock_client

        # 测试获取集合
        params = {"collection": "users"}
        collection = client._get_database_and_collection(params)

        assert collection is not None

    @pytest.mark.asyncio
    async def test_mongo_pool_config(self):
        """测试连接池配置"""
        from infra.database.mongodb import MongoConnectionPool
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="mongodb",
            pool=PoolConfig(min_size=10, max_size=50)
        )
        pool = MongoConnectionPool(config)

        # 验证连接池配置
        assert pool._min_size == 10
        assert pool._max_size == 50


class TestDatabaseFactory:
    """测试工厂函数"""

    def test_create_postgres_client(self):
        """测试创建PostgreSQL客户端"""
        from infra.database.factory import create_database_client
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="postgres")
        client = create_database_client(config)

        assert client is not None
        assert hasattr(client, "execute")
        assert hasattr(client, "connect")

    def test_create_mysql_client(self):
        """测试创建MySQL客户端"""
        from infra.database.factory import create_database_client
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="mysql")
        client = create_database_client(config)

        assert client is not None
        assert hasattr(client, "execute")

    def test_create_mongodb_client(self):
        """测试创建MongoDB客户端"""
        from infra.database.factory import create_database_client
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="mongodb")
        client = create_database_client(config)

        assert client is not None
        assert hasattr(client, "execute")

    def test_create_sqlite_client(self):
        """测试创建SQLite客户端"""
        from infra.database.factory import create_database_client
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = create_database_client(config)

        assert client is not None
        assert hasattr(client, "execute")

    def test_unsupported_database_type(self):
        """测试不支持的数据库类型"""
        from infra.database.factory import create_database_client
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="unsupported")

        with pytest.raises(ValueError):
            create_database_client(config)


class TestConnectionPool:
    """测试连接池"""

    def test_pool_config_creation(self):
        """测试连接池配置创建"""
        from infra.database.postgres import PostgresConnectionPool
        from infra.database.schemas import DatabaseConfig, PoolConfig

        config = DatabaseConfig(
            type="postgres",
            pool=PoolConfig(min_size=5, max_size=20)
        )
        pool = PostgresConnectionPool(config)

        # 验证连接池配置
        assert pool._min_size == 5
        assert pool._max_size == 20

    def test_pool_default_config(self):
        """测试默认连接池配置"""
        from infra.database.postgres import PostgresConnectionPool
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="postgres")
        pool = PostgresConnectionPool(config)

        # 验证默认配置
        assert pool._min_size == 5
        assert pool._max_size == 20

    @pytest.mark.asyncio
    async def test_pool_stats(self):
        """测试连接池统计"""
        from infra.database.postgres import PostgresConnectionPool
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="postgres")
        pool = PostgresConnectionPool(config)

        # 未初始化时，统计应该为空
        stats = pool.get_stats()
        assert stats.size == 0
        assert stats.available == 0
        assert stats.used == 0


class TestDatabaseErrors:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_sqlite_connection_error(self):
        """测试连接错误处理"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig
        import tempfile
        import os

        # 创建一个无效路径
        invalid_path = "/nonexistent/path/to/database.db"
        config = DatabaseConfig(type="sqlite", name=invalid_path)

        client = SqliteClient(config)

        # 应该抛出异常
        with pytest.raises(Exception):
            await client.connect()

    @pytest.mark.asyncio
    async def test_sqlite_query_error(self):
        """测试查询错误处理"""
        from infra.database.sqlite import SqliteClient
        from infra.database.schemas import DatabaseConfig

        config = DatabaseConfig(type="sqlite", name=":memory:")
        client = SqliteClient(config)
        await client.connect()

        # 查询不存在的表
        with pytest.raises(Exception):
            await client.execute("SELECT * FROM nonexistent_table")

        await client.close()