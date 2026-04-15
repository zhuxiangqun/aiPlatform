#!/usr/bin/env python3
"""
数据库集成测试主运行器

运行所有数据库的真实集成测试

使用方法:
    cd aiPlat-infra
    python infra/tests/test_database/run_all_integration_tests.py
    
    # 或单独运行
    python infra/tests/test_database/test_postgres_integration.py
    python infra/tests/test_database/test_mysql_integration.py
    python infra/tests/test_database/test_mongodb_integration.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime


async def run_postgres_test():
    """运行PostgreSQL测试"""
    print("\n" + "="*70)
    print("🔍 运行 PostgreSQL 集成测试...")
    print("="*70)
    
    try:
        # 动态导入避免循环依赖
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        from testcontainers.postgres import PostgresContainer
        from infra.database.postgres import PostgresClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        print("[1/5] 启动容器...")
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        print("✓ PostgreSQL容器已启动")
        
        url = container.get_connection_url()
        parsed = urllib.parse.urlparse(url)
        config = DatabaseConfig(
            type="postgres",
            host=parsed.hostname,
            port=parsed.port,
            user=parsed.username,
            password=parsed.password,
            name=parsed.path.lstrip('/')
        )
        
        print("[2/5] 连接数据库...")
        client = PostgresClient(config)
        await client.connect()
        print("✓ 连接成功")
        
        print("[3/5] 执行测试...")
        # 创建表
        await client.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id SERIAL PRIMARY KEY,
                test_name VARCHAR(100),
                status VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 插入数据
        await client.execute(
            "INSERT INTO test_results (test_name, status) VALUES ($1, $2)",
            ("PostgreSQL Integration Test", "PASS")
        )
        
        # 查询数据
        results = await client.execute("SELECT * FROM test_results")
        assert len(results) == 1
        assert results[0]["test_name"] == "PostgreSQL Integration Test"
        print(f"✓ 测试通过: 查询到 {len(results)} 条记录")
        
        # 清理
        print("[4/5] 清理数据...")
        await client.execute("DROP TABLE IF EXISTS test_results")
        await client.close()
        print("✓ 数据已清理")
        
        print("[5/5] 停止容器...")
        container.stop()
        print("✓ PostgreSQL容器已停止")
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_mysql_test():
    """运行MySQL测试"""
    print("\n" + "="*70)
    print("🔍 运行 MySQL 集成测试...")
    print("="*70)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        from testcontainers.mysql import MySqlContainer
        from infra.database.mysql import MySqlClient
        from infra.database.schemas import DatabaseConfig
        import urllib.parse
        
        print("[1/5] 启动容器...")
        container = MySqlContainer("mysql:8.0")
        container.start()
        print("✓ MySQL容器已启动")
        
        url = container.get_connection_url()
        parsed = urllib.parse.urlparse(url)
        config = DatabaseConfig(
            type="mysql",
            host=parsed.hostname,
            port=parsed.port,
            user=parsed.username,
            password=parsed.password,
            name=parsed.path.lstrip('/')
        )
        
        print("[2/5] 连接数据库...")
        client = MySqlClient(config)
        await client.connect()
        print("✓ 连接成功")
        
        print("[3/5] 执行测试...")
        # 创建表
        await client.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                test_name VARCHAR(100),
                status VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 插入数据
        await client.execute(
            "INSERT INTO test_results (test_name, status) VALUES (%s, %s)",
            ("MySQL Integration Test", "PASS")
        )
        
        # 查询数据
        results = await client.execute("SELECT * FROM test_results")
        assert len(results) == 1
        assert results[0]["test_name"] == "MySQL Integration Test"
        print(f"✓ 测试通过: 查询到 {len(results)} 条记录")
        
        # 清理
        print("[4/5] 清理数据...")
        await client.execute("DROP TABLE IF EXISTS test_results")
        await client.close()
        print("✓ 数据已清理")
        
        print("[5/5] 停止容器...")
        container.stop()
        print("✓ MySQL容器已停止")
        
        return True
        
    except Exception as e:
        print(f"❌ MySQL测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_mongodb_test():
    """运行MongoDB测试"""
    print("\n" + "="*70)
    print("🔍 运行 MongoDB 集成测试...")
    print("="*70)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        from testcontainers.mongodb import MongoDbContainer
        from infra.database.mongodb import MongoClient
        from infra.database.schemas import DatabaseConfig
        
        print("[1/5] 启动容器...")
        print("⚠️  注意: MongoDB镜像较大，首次运行需下载 (~700MB)")
        container = MongoDbContainer("mongo:7.0")
        container.start()
        print("✓ MongoDB容器已启动")
        
        host = container.get_container_host_ip()
        port = container.get_exposed_port(27017)
        
        # MongoDbContainer默认用户名和密码都是"test"
        config = DatabaseConfig(
            type="mongodb",
            host=host,
            port=port,
            name="test_db",
            user="test",  # MongoDbContainer默认用户
            password="test"  # MongoDbContainer默认密码
        )
        
        print("[2/5] 连接数据库...")
        client = MongoClient(config)
        await client.connect()
        print("✓ 连接成功")
        
        print("[3/5] 执行测试...")
        # 插入文档
        result = await client.execute(
            "insert_one",
            {
                "collection": "test_results",
                "document": {
                    "test_name": "MongoDB Integration Test",
                    "status": "PASS",
                    "timestamp": datetime.now()
                }
            }
        )
        assert result[0]["inserted_id"] is not None
        print(f"✓ 插入文档成功: {result[0]['inserted_id']}")
        
        # 查询文档
        results = await client.execute(
            "find",
            {
                "collection": "test_results",
                "filter": {"test_name": "MongoDB Integration Test"}
            }
        )
        assert len(results) == 1
        assert results[0]["status"] == "PASS"
        print(f"✓ 测试通过: 查询到 {len(results)} 条文档")
        
        # 清理
        print("[4/5] 清理数据...")
        await client.execute(
            "delete_many",
            {
                "collection": "test_results",
                "filter": {}
            }
        )
        await client.close()
        print("✓ 数据已清理")
        
        print("[5/5] 停止容器...")
        container.stop()
        print("✓ MongoDB容器已停止")
        
        return True
        
    except Exception as e:
        print(f"❌ MongoDB测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试运行器"""
    print("\n" + "="*70)
    print("        AI Platform - 数据库集成测试套件")
    print("="*70)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n⚠️  注意: 这些测试需要Docker运行，会启动真实的数据库容器")
    print("每个测试会独立启动和停止容器\n")
    
    results = {}
    
    # 运行所有测试
    results["PostgreSQL"] = await run_postgres_test()
    results["MySQL"] = await run_mysql_test()
    
    # MongoDB测试（可选，因为镜像较大）
    print("\n" + "="*70)
    print("⚠️  MongoDB测试需要下载~700MB镜像，是否继续？")
    response = input("继续运行MongoDB测试吗？(y/n): ").strip().lower()
    if response == 'y':
        results["MongoDB"] = await run_mongodb_test()
    else:
        print("跳过MongoDB测试")
        results["MongoDB"] = "SKIPPED"
    
    # 总结
    print("\n" + "="*70)
    print("                      测试结果汇总")
    print("="*70)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    for db, status in results.items():
        if status == True:
            print(f"✅ {db:15s} PASSED")
        elif status == "SKIPPED":
            print(f"⏭️  {db:15s} SKIPPED")
        else:
            print(f"❌ {db:15s} FAILED")
    
    print("="*70)
    
    # 统计
    passed = sum(1 for s in results.values() if s == True)
    failed = sum(1 for s in results.values() if s == False)
    skipped = sum(1 for s in results.values() if s == "SKIPPED")
    
    print(f"\n总计: {len(results)} 个测试")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"⏭️  跳过: {skipped}")
    
    if failed == 0 and skipped >= 0:
        print("\n🎉 所有运行的测试通过！")
        return 0
    elif failed > 0:
        print("\n❌ 部分测试失败，请检查错误日志")
        return 1
    else:
        print("\n✅ 测试通过（部分跳过）")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)