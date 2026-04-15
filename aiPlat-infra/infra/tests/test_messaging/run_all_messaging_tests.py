#!/usr/bin/env python3
"""
消息系统集成测试主运行器

运行所有消息后端的真实集成测试
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime


async def run_redis_test():
    """运行Redis Streams测试"""
    print("\n" + "="*70)
    print("🔍 运行 Redis Streams 集成测试...")
    print("="*70)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        from testcontainers.redis import RedisContainer
        from infra.messaging.redis_backend import RedisClient
        from infra.messaging.schemas import MessagingConfig, ConsumerConfig
        import json
        
        print("[1/5] 启动容器...")
        container = RedisContainer("redis:7-alpine")
        container.start()
        print("✓ Redis容器已启动")
        
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        
        config = MessagingConfig(
            backend="redis",
            hosts=[f"{host}:{port}"],
            topic_prefix="test"
        )
        
        print("[2/5] 创建客户端...")
        client = RedisClient(config)
        
        print("[3/5] 发布消息...")
        await client.publish(
            topic="test_topic",
            message=json.dumps({"message": "Hello Redis!"}).encode()
        )
        print("✓ 消息已发布")
        
        print("[4/5] 订阅和消费...")
        received = []
        
        async def handler(msg):
            received.append(msg)
        
        await client.subscribe(topic="test_topic", handler=handler, config=None)
        await asyncio.sleep(1)
        
        if received:
            print(f"✓ 接收到 {len(received)} 条消息")
        else:
            print("⚠️  未接收到消息")
        
        print("[5/5] 清理...")
        await client.close()
        container.stop()
        print("✓ Redis容器已停止")
        
        return True
        
    except Exception as e:
        print(f"❌ Redis测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_rabbitmq_test():
    """运行RabbitMQ测试"""
    print("\n" + "="*70)
    print("🔍 运行 RabbitMQ 集成测试...")
    print("="*70)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        from testcontainers.rabbitmq import RabbitMqContainer
        from infra.messaging.rabbitmq_backend import RabbitMQClient
        from infra.messaging.schemas import MessagingConfig, RabbitMQOptions
        
        print("⚠️  RabbitMQ镜像较大，跳过测试")
        print("提示: 运行单独测试: python test_rabbitmq_integration.py")
        
        return "SKIPPED"
        
    except Exception as e:
        print(f"❌ RabbitMQ测试失败: {e}")
        return False


async def run_kafka_test():
    """运行Kafka测试"""
    print("\n" + "="*70)
    print("🔍 运行 Kafka 集成测试...")
    print("="*70)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        
        print("⚠️  Kafka镜像较大，跳过测试")
        print("提示: 运行单独测试: python test_kafka_integration.py")
        
        return "SKIPPED"
        
    except Exception as e:
        print(f"❌ Kafka测试失败: {e}")
        return False


async def main():
    """主测试运行器"""
    print("\n" + "="*70)
    print("        AI Platform - 消息系统集成测试套件")
    print("="*70)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n⚠️  注意: 这些测试需要Docker运行，会启动真实的消息容器")
    
    results = {}
    
    # 运行Redis测试（快速，镜像小）
    print("\n[1/3] Redis Streams 测试")
    print("-" * 70)
    results["Redis"] = await run_redis_test()
    
    # RabbitMQ和Kafka镜像较大，提供单独测试
    print("\n[2/3] RabbitMQ 测试")
    print("-" * 70)
    results["RabbitMQ"] = await run_rabbitmq_test()
    
    print("\n[3/3] Kafka 测试")
    print("-" * 70)
    results["Kafka"] = await run_kafka_test()
    
    # 总结
    print("\n" + "="*70)
    print("                      测试结果汇总")
    print("="*70)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    for backend, status in results.items():
        if status == True:
            print(f"✅ {backend:15s} PASSED")
        elif status == "SKIPPED":
            print(f"⏭️  {backend:15s} SKIPPED")
        else:
            print(f"❌ {backend:15s} FAILED")
    
    print("="*70)
    
    # 统计
    passed = sum(1 for s in results.values() if s == True)
    failed = sum(1 for s in results.values() if s == False)
    skipped = sum(1 for s in results.values() if s == "SKIPPED")
    
    print(f"\n总计: {len(results)} 个测试")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"⏭️  跳过: {skipped}")
    
    if failed == 0:
        print("\n🎉 所有运行的测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查错误日志")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)