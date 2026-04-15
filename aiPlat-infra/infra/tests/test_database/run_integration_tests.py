#!/usr/bin/env python3
"""
简化的集成测试运行器 - 逐个测试运行并显示进度
"""
import asyncio
import sys
import os
from pathlib import Path

# 在aiPlat-infra目录下运行，所以python路径应该包含当前目录
# run_integration_tests.py 在 aiPlat-infra/infra/tests/test_database/
# 我们需要从aiPlat-infra目录导入infra包
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent
sys.path.insert(0, str(project_root))


async def test_postgres():
    """测试PostgreSQL集成"""
    from testcontainers.postgres import PostgresContainer
    from infra.database.postgres import PostgresClient
    from infra.database.schemas import DatabaseConfig
    import urllib.parse
    
    print("\n" + "="*60)
    print("启动 PostgreSQL 容器...")
    print("="*60)
    
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    
    try:
        connection_url = container.get_connection_url()
        print(f"✓ 容器已启动: {connection_url}\n")
        
        # 解析连接信息
        parsed = urllib.parse.urlparse(connection_url)
        
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
        
        # 测试1: 连接测试
        print("测试1: 连接PostgreSQL...")
        result = await client.execute("SELECT version()")
        assert len(result) == 1
        assert "PostgreSQL" in result[0]["version"]
        print("✓ 连接成功\n")
        
        # 测试2: 创建表和插入数据
        print("测试2: 创建表和插入数据...")
        await client.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                age INTEGER
            )
        """)
        
        await client.execute(
            "INSERT INTO users (name, email, age) VALUES ($1, $2, $3)",
            ("Alice", "alice@example.com", 30)
        )
        
        await client.execute(
            "INSERT INTO users (name, email, age) VALUES ($1, $2, $3)",
            ("Bob", "bob@example.com", 25)
        )
        
        results = await client.execute("SELECT * FROM users ORDER BY age")
        assert len(results) == 2
        assert results[0]["name"] == "Bob"
        print(f"✓ 插入 {len(results)} 条数据成功\n")
        
        # 测试3: 事务测试
        print("测试3: 测试事务提交和回滚...")
        await client.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                balance DECIMAL(10, 2)
            )
        """)
        
        await client.execute(
            "INSERT INTO accounts (name, balance) VALUES ($1, $2)",
            ("Charlie", 100.00)
        )
        
        # 测试事务提交
        async with client.transaction():
            await client.execute(
                "UPDATE accounts SET balance = $1 WHERE name = $2",
                (150.00, "Charlie")
            )
        
        results = await client.execute("SELECT balance FROM accounts WHERE name = 'Charlie'")
        assert float(results[0]["balance"]) == 150.00
        print("✓ 事务提交成功")
        
        # 测试事务回滚
        try:
            async with client.transaction():
                await client.execute(
                    "UPDATE accounts SET balance = $1 WHERE name = $2",
                    (999.00, "Charlie")
                )
                raise Exception("Test rollback")
        except:
            pass
        
        results = await client.execute("SELECT balance FROM accounts WHERE name = 'Charlie'")
        assert float(results[0]["balance"]) == 150.00  # 应该保持150
        print("✓ 事务回滚成功\n")
        
        # 清理
        await client.execute("DROP TABLE IF EXISTS users")
        await client.execute("DROP TABLE IF EXISTS accounts")
        await client.close()
        
        print("="*60)
        print("✅ PostgreSQL集成测试全部通过！")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        container.stop()
        print("\n容器已停止")


async def test_mysql():
    """测试MySQL集成"""
    from testcontainers.mysql import MySqlContainer
    from infra.database.mysql import MySqlClient
    from infra.database.schemas import DatabaseConfig
    import urllib.parse
    
    print("\n" + "="*60)
    print("启动 MySQL 容器...")
    print("="*60)
    
    container = MySqlContainer("mysql:8.0")
    container.start()
    
    try:
        connection_url = container.get_connection_url()
        print(f"✓ 容器已启动\n")
        
        parsed = urllib.parse.urlparse(connection_url)
        
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
        
        # 测试创建表和插入数据
        print("测试: 创建表和插入数据...")
        await client.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2),
                stock INT
            )
        """)
        
        await client.execute(
            "INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)",
            ("Laptop", 999.99, 10)
        )
        
        await client.execute(
            "INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)",
            ("Mouse", 29.99, 100)
        )
        
        results = await client.execute("SELECT * FROM products ORDER BY price DESC")
        assert len(results) == 2
        assert results[0]["name"] == "Laptop"
        print(f"✓ 插入 {len(results)} 条数据成功\n")
        
        # 清理
        await client.execute("DROP TABLE IF EXISTS products")
        await client.close()
        
        print("="*60)
        print("✅ MySQL集成测试全部通过！")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        container.stop()
        print("\n容器已停止")


async def test_mongodb():
    """测试MongoDB集成"""
    from testcontainers.mongodb import MongoDbContainer
    from infra.database.mongodb import MongoClient
    from infra.database.schemas import DatabaseConfig
    
    print("\n" + "="*60)
    print("启动 MongoDB 容器...")
    print("="*60)
    
    container = MongoDbContainer("mongo:7.0")
    container.start()
    
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(27017)
        print(f"✓ 容器已启动: mongodb://{host}:{port}\n")
        
        config = DatabaseConfig(
            type="mongodb",
            host=host,
            port=port,
            name="test_integration"
        )
        
        client = MongoClient(config)
        await client.connect()
        
        # 测试插入和查询文档
        print("测试: 插入和查询文档...")
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
        print(f"✓ 插入 {len(results)} 条文档成功\n")
        
        # 更新文档
        update_result = await client.execute(
            "update_one",
            {
                "collection": "users",
                "filter": {"name": "Alice"},
                "update": {"$set": {"age": 35}}
            }
        )
        assert update_result[0]["modified_count"] == 1
        print("✓ 更新文档成功\n")
        
        # 删除文档
        delete_result = await client.execute(
            "delete_one",
            {
                "collection": "users",
                "filter": {"name": "Bob"}
            }
        )
        assert delete_result[0]["deleted_count"] == 1
        print("✓ 删除文档成功\n")
        
        await client.close()
        
        print("="*60)
        print("✅ MongoDB集成测试全部通过！")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        container.stop()
        print("\n容器已停止")


async def main():
    """主测试运行器"""
    print("\n" + "="*70)
    print("        AI Platform - 数据库集成测试")
    print("="*70)
    print("\n注意: 这些测试需要Docker运行，会启动真实的数据库容器")
    print("每个测试会独立启动和停止容器，请耐心等待...\n")
    
    results = {}
    
    # PostgreSQL测试
    print("\n[1/3] PostgreSQL 集成测试")
    print("-" * 70)
    results["PostgreSQL"] = await test_postgres()
    
    # MySQL测试
    print("\n[2/3] MySQL 集成测试")
    print("-" * 70)
    results["MySQL"] = await test_mysql()
    
    # MongoDB测试
    print("\n[3/3] MongoDB 集成测试")
    print("-" * 70)
    results["MongoDB"] = await test_mongodb()
    
    # 总结
    print("\n" + "="*70)
    print("                      测试结果汇总")
    print("="*70)
    for db, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{db:15s} {status}")
    print("="*70)
    
    # 返回码
    if all(results.values()):
        print("\n🎉 所有集成测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败，请检查错误日志")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())