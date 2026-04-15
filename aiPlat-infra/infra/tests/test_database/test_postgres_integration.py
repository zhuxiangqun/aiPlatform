#!/usr/bin/env python3
"""
PostgreSQL集成测试 - 单独测试

运行方式: cd aiPlat-infra && python infra/tests/test_database/test_postgres_integration.py
"""
import asyncio
from testcontainers.postgres import PostgresContainer
import sys
from pathlib import Path

# 添加项目根目录到Python路径
# 当前文件在: aiPlat-infra/infra/tests/test_database/test_postgres_integration.py
# 项目根目录: aiPlat-infra/
project_root = Path(__file__).resolve().parent.parent.parent.parent  # 从test_postgres_integration.py往上4级
sys.path.insert(0, str(project_root))

print(f"Project root: {project_root}")
print(f"Python path: {sys.path[0]}")

from infra.database.postgres import PostgresClient
from infra.database.schemas import DatabaseConfig
import urllib.parse


async def test_postgres_integration():
    """PostgreSQL完整集成测试"""
    print("\n" + "="*70)
    print("PostgreSQL 集成测试")
    print("="*70)
    
    print("\n[1/7] 启动PostgreSQL容器...")
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    print("✓ 容器已启动")
    
    try:
        connection_url = container.get_connection_url()
        print(f"[2/7] 连接URL: {connection_url}")
        
        # 解析配置
        parsed = urllib.parse.urlparse(connection_url)
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        # 创建客户端
        print("[3/7] 创建PostgreSQL客户端...")
        client = PostgresClient(config)
        
        # 连接
        print("[4/7] 连接数据库...")
        await client.connect()
        print("✓ 连接成功")
        
        # 测试查询
        print("[5/7] 执行测试查询...")
        result = await client.execute("SELECT version()")
        print(f"✓ PostgreSQL版本: {result[0]['version'][:50]}...")
        
        # 创建表
        print("[6/7] 创建表并插入数据...")
        await client.execute("""
            CREATE TABLE IF NOT EXISTS test_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255)
            )
        """)
        
        # 插入数据
        await client.execute(
            "INSERT INTO test_users (name, email) VALUES ($1, $2)",
            ("Alice", "alice@example.com")
        )
        
        await client.execute(
            "INSERT INTO test_users (name, email) VALUES ($1, $2)",
            ("Bob", "bob@example.com")
        )
        
        # 查询数据
        results = await client.execute("SELECT * FROM test_users ORDER BY id")
        print(f"✓ 插入并查询到 {len(results)} 条数据:")
        for row in results:
            print(f"  - ID: {row['id']}, Name: {row['name']}, Email: {row['email']}")
        
        # 清理
        await client.execute("DROP TABLE IF EXISTS test_users")
        
        # 关闭连接
        print("[7/7] 关闭连接...")
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ PostgreSQL集成测试成功！")
        print("="*70)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n停止容器...")
        container.stop()
        print("✓ 容器已停止")


if __name__ == "__main__":
    asyncio.run(test_postgres_integration())