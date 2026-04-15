#!/usr/bin/env python3
"""
MySQL集成测试 - 单独测试

运行方式: cd aiPlat-infra && python infra/tests/test_database/test_mysql_integration.py
"""
import asyncio
from testcontainers.mysql import MySqlContainer
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.database.mysql import MySqlClient
from infra.database.schemas import DatabaseConfig
import urllib.parse


async def test_mysql_integration():
    """MySQL完整集成测试"""
    print("\n" + "="*70)
    print("MySQL 集成测试")
    print("="*70)
    
    print("\n[1/7] 启动MySQL容器...")
    container = MySqlContainer("mysql:8.0")
    container.start()
    print("✓ 容器已启动")
    
    try:
        connection_url = container.get_connection_url()
        print(f"[2/7] 连接URL: {connection_url}")
        
        # 解析配置
        parsed = urllib.parse.urlparse(connection_url)
        config = DatabaseConfig(
            type="mysql",
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "test",
            password=parsed.password or "test",
            name=parsed.path.lstrip('/') or "test"
        )
        
        # 创建客户端
        print("[3/7] 创建MySQL客户端...")
        client = MySqlClient(config)
        
        # 连接
        print("[4/7] 连接数据库...")
        await client.connect()
        print("✓ 连接成功")
        
        # 测试查询
        print("[5/7] 执行测试查询...")
        result = await client.execute("SELECT VERSION()")
        print(f"✓ MySQL版本: {result[0]['VERSION()']}")
        
        # 创建表
        print("[6/7] 创建表并插入数据...")
        await client.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2),
                stock INT
            )
        """)
        
        # 插入数据 - MySQL使用%s占位符
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
        print(f"✓ 插入并查询到 {len(results)} 条数据:")
        for row in results:
            print(f"  - ID: {row['id']}, Name: {row['name']}, Price: ${row['price']}, Stock: {row['stock']}")
        
        # 清理
        await client.execute("DROP TABLE IF EXISTS products")
        
        # 关闭连接
        print("[7/7] 关闭连接...")
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ MySQL集成测试成功！")
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
    asyncio.run(test_mysql_integration())