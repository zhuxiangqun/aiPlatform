#!/usr/bin/env python3
"""
MongoDB集成测试 - 单独测试

运行方式: cd aiPlat-infra && python infra/tests/test_database/test_mongodb_integration.py
"""
import asyncio
from testcontainers.mongodb import MongoDbContainer
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.database.mongodb import MongoClient
from infra.database.schemas import DatabaseConfig


async def test_mongodb_integration():
    """MongoDB完整集成测试"""
    print("\n" + "="*70)
    print("MongoDB 集成测试")
    print("="*70)
    
    print("\n[1/7] 启动MongoDB容器...")
    container = MongoDbContainer("mongo:7.0")
    container.start()
    print("✓ 容器已启动")
    
    try:
        # 获取连接信息
        host = container.get_container_host_ip()
        port = container.get_exposed_port(27017)
        
        # MongoDbContainer默认用户名和密码都是"test"
        connection_url = container.get_connection_url()
        print(f"[2/7] 连接URL: {connection_url}")
        
        # 配置 - 使用容器的认证信息
        config = DatabaseConfig(
            type="mongodb",
            host=host,
            port=port,
            name="test_db",
            user="test",  # MongoDbContainer默认用户
            password="test"  # MongoDbContainer默认密码
        )
        
        # 创建客户端
        print("[3/7] 创建MongoDB客户端...")
        client = MongoClient(config)
        
        # 连接
        print("[4/7] 连接数据库...")
        await client.connect()
        print("✓ 连接成功")
        
        # 测试插入和查询
        print("[5/7] 插入文档...")
        
        # 插入多个文档
        result1 = await client.execute(
            "insert_one",
            {
                "collection": "users",
                "document": {"name": "Alice", "age": 30, "email": "alice@example.com"}
            }
        )
        print(f"✓ 插入文档ID: {result1[0]['inserted_id']}")
        
        result2 = await client.execute(
            "insert_one",
            {
                "collection": "users",
                "document": {"name": "Bob", "age": 25, "email": "bob@example.com"}
            }
        )
        print(f"✓ 插入文档ID: {result2[0]['inserted_id']}")
        
        # 查询文档
        print("[6/7] 查询文档...")
        results = await client.execute(
            "find",
            {
                "collection": "users",
                "filter": {"age": {"$gt": 20}}
            }
        )
        print(f"✓ 查询到 {len(results)} 条文档:")
        for doc in results:
            print(f"  - Name: {doc.get('name')}, Age: {doc.get('age')}, Email: {doc.get('email')}")
        
        # 更新文档
        update_result = await client.execute(
            "update_one",
            {
                "collection": "users",
                "filter": {"name": "Alice"},
                "update": {"$set": {"age": 35}}
            }
        )
        print(f"✓ 更新了 {update_result[0]['modified_count']} 条文档")
        
        # 删除文档
        delete_result = await client.execute(
            "delete_one",
            {
                "collection": "users",
                "filter": {"name": "Bob"}
            }
        )
        print(f"✓ 删除了 {delete_result[0]['deleted_count']} 条文档")
        
        # 验证删除
        final_results = await client.execute(
            "find",
            {
                "collection": "users",
                "filter": {}
            }
        )
        print(f"✓ 最终剩余 {len(final_results)} 条文档")
        
        # 关闭连接
        print("[7/7] 关闭连接...")
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ MongoDB集成测试成功！")
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
    asyncio.run(test_mongodb_integration())