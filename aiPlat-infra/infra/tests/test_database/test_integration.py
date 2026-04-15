"""
数据库集成测试 - 使用Testcontainers进行真实数据库测试

这些测试需要Docker来运行，会自动启动和停止数据库容器。
运行方式: pytest infra/tests/test_database/test_integration.py -v -s
"""
import pytest
import asyncio
from typing import AsyncGenerator


# ============================================
# PostgreSQL 真实数据库测试
# ============================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestPostgreSQLIntegration:
    """PostgreSQL真实数据库操作测试"""

    async def test_postgres_connection(self, postgres_container):
        """测试连接到PostgreSQL容器"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        # 解析连接URL
        parsed = urllib.parse.urlparse(postgres_container)
        
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = PostgresClient(config)
        
        # 连接到真实数据库
        await client.connect()
        
        # 验证连接池已创建
        assert client._pool is not None
        
        # 执行简单查询验证连接
        result = await client.execute("SELECT version()")
        assert len(result) == 1
        assert "PostgreSQL" in result[0]["version"]
        
        # 关闭连接
        await client.close()

    async def test_postgres_create_table_and_insert(self, postgres_container):
        """测试创建表和插入数据"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(postgres_container)
        
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = PostgresClient(config)
        await client.connect()
        
        try:
            # 创建表
            await client.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    age INTEGER
                )
            """)
            
            # 插入数据（使用位置参数）
            await client.execute(
                "INSERT INTO users (name, email, age) VALUES ($1, $2, $3)",
                ("Alice", "alice@example.com", 30)
            )
            
            await client.execute(
                "INSERT INTO users (name, email, age) VALUES ($1, $2, $3)",
                ("Bob", "bob@example.com", 25)
            )
            
            # 查询数据
            results = await client.execute("SELECT * FROM users ORDER BY age")
            
            assert len(results) == 2
            assert results[0]["name"] == "Bob"  # 年龄25，排第一
            assert results[0]["age"] == 25
            assert results[1]["name"] == "Alice"
            assert results[1]["age"] == 30
        finally:
            # 清理
            await client.execute("DROP TABLE IF EXISTS users")
            await client.close()

    async def test_postgres_transaction_commit(self, postgres_container):
        """测试事务提交"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(postgres_container)
        
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = PostgresClient(config)
        await client.connect()
        
        try:
            # 创建表
            await client.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    balance DECIMAL(10, 2)
                )
            """)
            
            # 插入初始数据
            await client.execute(
                "INSERT INTO accounts (name, balance) VALUES ($1, $2)",
                ("Alice", 100.00)
            )
            
            # 测试事务提交
            async with client.transaction():
                await client.execute(
                    "UPDATE accounts SET balance = $1 WHERE name = $2",
                    (150.00, "Alice")
                )
            
            # 验证事务已提交
            results = await client.execute("SELECT balance FROM accounts WHERE name = 'Alice'")
            assert len(results) == 1
            assert float(results[0]["balance"]) == 150.00
        finally:
            # 清理
            await client.execute("DROP TABLE IF EXISTS accounts")
            await client.close()

    async def test_postgres_transaction_rollback(self, postgres_container):
        """测试事务回滚"""
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(postgres_container)
        
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = PostgresClient(config)
        await client.connect()
        
        try:
            # 创建表
            await client.execute("""
                CREATE TABLE IF NOT EXISTS accounts_rollback (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    balance DECIMAL(10, 2)
                )
            """)
            
            # 插入初始数据
            await client.execute(
                "INSERT INTO accounts_rollback (name, balance) VALUES ($1, $2)",
                ("Bob", 200.00)
            )
            
            # 测试事务回滚
            try:
                async with client.transaction():
                    await client.execute(
                        "UPDATE accounts_rollback SET balance = $1 WHERE name = $2",
                        (500.00, "Bob")
                    )
                    raise Exception("Simulated error to trigger rollback")
            except Exception:
                pass
            
            # 验证事务已回滚
            results = await client.execute("SELECT balance FROM accounts_rollback WHERE name = 'Bob'")
            assert len(results) == 1
            assert float(results[0]["balance"]) == 200.00  # 应该是原始值
        finally:
            # 清理
            await client.execute("DROP TABLE IF EXISTS accounts_rollback")
            await client.close()


# ============================================
# MySQL 真实数据库测试
# ============================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestMySQLIntegration:
    """MySQL真实数据库操作测试"""

    async def test_mysql_connection(self, mysql_container):
        """测试连接到MySQL容器"""
        from infra.database.mysql import MySqlClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        # 解析连接URL
        parsed = urllib.parse.urlparse(mysql_container)
        
        config = DatabaseConfig(
            type="mysql",
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = MySqlClient(config)
        
        # 连接到真实数据库
        await client.connect()
        
        # 验证连接
        assert client._pool is not None
        
        # 关闭连接
        await client.close()

    async def test_mysql_create_table_and_query(self, mysql_container):
        """测试创建表和查询"""
        from infra.database.mysql import MySqlClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(mysql_container)
        
        config = DatabaseConfig(
            type="mysql",
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = MySqlClient(config)
        await client.connect()
        
        # 创建表
        await client.execute("""
            CREATE TABLE products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2),
                stock INT
            )
        """)
        
        # 插入数据
        await client.execute(
            "INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)",
            ("Laptop", 999.99, 10)
        )
        
        await client.execute(
            "INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)",
            ("Mouse", 29.99, 100)
        )
        
        # 查询数据
        results = await client.execute("SELECT * FROM products ORDER BY price DESC")
        
        assert len(results) == 2
        assert results[0]["name"] == "Laptop"
        assert float(results[0]["price"]) == 999.99
        assert results[1]["name"] == "Mouse"
        assert float(results[1]["price"]) == 29.99
        
        await client.close()


# ============================================
# MongoDB 真实数据库测试
# ============================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestMongoDBIntegration:
    """MongoDB真实数据库操作测试"""

    async def test_mongodb_connection(self, mongodb_container):
        """测试连接到MongoDB容器"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        # 解析连接URL
        parsed = urllib.parse.urlparse(mongodb_container)
        
        config = DatabaseConfig(
            type="mongodb",
            host=parsed.hostname or "localhost",
            port=parsed.port or 27017,
            name=parsed.path.lstrip('/') or "test"
        )
        
        client = MongoClient(config)
        
        # 连接到真实数据库
        await client.connect()
        
        # 验证连接
        assert client._client is not None
        
        # 关闭连接
        await client.close()

    async def test_mongodb_insert_and_find(self, mongodb_container):
        """测试插入和查询文档"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(mongodb_container)
        
        config = DatabaseConfig(
            type="mongodb",
            host=parsed.hostname or "localhost",
            port=parsed.port or 27017,
            name="test_" + str(hash("test"))[:8]  # 随机数据库名避免冲突
        )
        
        client = MongoClient(config)
        await client.connect()
        
        # 插入文档
        result1 = await client.execute(
            "insert_one",
            {
                "collection": "users",
                "document": {"name": "Alice", "age": 30, "email": "alice@example.com"}
            }
        )
        assert result1[0]["inserted_id"] is not None
        
        result2 = await client.execute(
            "insert_one",
            {
                "collection": "users",
                "document": {"name": "Bob", "age": 25, "email": "bob@example.com"}
            }
        )
        assert result2[0]["inserted_id"] is not None
        
        # 查询文档
        results = await client.execute(
            "find",
            {
                "collection": "users",
                "filter": {"age": {"$gt": 20}}
            }
        )
        
        assert len(results) == 2
        
        # 查询单个文档
        result = await client.execute(
            "find_one",
            {
                "collection": "users",
                "filter": {"name": "Alice"}
            }
        )
        assert len(result) > 0
        assert result[0]["name"] == "Alice"
        
        await client.close()

    async def test_mongodb_update_and_delete(self, mongodb_container):
        """测试更新和删除文档"""
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        parsed = urllib.parse.urlparse(mongodb_container)
        
        config = DatabaseConfig(
            type="mongodb",
            host=parsed.hostname or "localhost",
            port=parsed.port or 27017,
            name="test_" + str(hash("update"))[:8]
        )
        
        client = MongoClient(config)
        await client.connect()
        
        # 插入测试数据
        await client.execute(
            "insert_one",
            {
                "collection": "products",
                "document": {"name": "Widget", "price": 100, "stock": 50}
            }
        )
        
        # 更新文档
        update_result = await client.execute(
            "update_one",
            {
                "collection": "products",
                "filter": {"name": "Widget"},
                "update": {"$set": {"price": 150}}
            }
        )
        assert update_result[0]["modified_count"] == 1
        
        # 验证更新
        results = await client.execute(
            "find",
            {
                "collection": "products",
                "filter": {"name": "Widget"}
            }
        )
        assert len(results) == 1
        assert results[0]["price"] == 150
        
        # 删除文档
        delete_result = await client.execute(
            "delete_one",
            {
                "collection": "products",
                "filter": {"name": "Widget"}
            }
        )
        assert delete_result[0]["deleted_count"] == 1
        
        # 验证删除
        results = await client.execute(
            "find",
            {
                "collection": "products",
                "filter": {"name": "Widget"}
            }
        )
        assert len(results) == 0
        
        await client.close()


# ============================================
# Redis 测试（如果已有Redis容器）
# ============================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisIntegration:
    """Redis真实操作测试"""

    @pytest.mark.skip(reason="Redis integration test not implemented yet")
    async def test_redis_connection(self, redis_container):
        """测试Redis连接"""
        pass


# ============================================
# 辅助函数
# ============================================

def pytest_collection_modifyitems(config, items):
    """为所有集成测试添加标记"""
    for item in items:
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)