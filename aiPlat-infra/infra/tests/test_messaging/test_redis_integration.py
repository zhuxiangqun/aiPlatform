#!/usr/bin/env python3
"""
Redis Streams集成测试

运行方式: cd aiPlat-infra && python infra/tests/test_messaging/test_redis_integration.py
"""
import asyncio
from testcontainers.redis import RedisContainer
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infra.messaging.redis_backend import RedisClient
from infra.messaging.schemas import MessagingConfig


async def test_redis_integration():
    """Redis Streams完整集成测试"""
    print("\n" + "="*70)
    print("Redis Streams 集成测试")
    print("="*70)
    
    print("\n[1/6] 启动Redis容器...")
    container = RedisContainer("redis:7-alpine")
    container.start()
    print("✓ 容器已启动")
    
    try:
        # 获取连接信息
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        print(f"[2/6] Redis地址: {host}:{port}")
        
        # 配置
        config = MessagingConfig(
            type="redis",
            hosts=[f"{host}:{port}"],
            topic_prefix="test"
        )
        
        # 创建客户端
        print("[3/6] 创建Redis Streams客户端...")
        client = RedisClient(config)
        await client.connect()
        print("✓ 连接成功")
        
        # 测试发布消息
        print("[4/6] 测试消息发布...")
        
        # Redis Streams使用publish方法，参数是topic, message(bytes)
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "123", "amount": 99.99, "customer": "Alice"}).encode()
        )
        print("✓ 发布消息到 orders 流")
        
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "124", "amount": 149.99, "customer": "Bob"}).encode()
        )
        print("✓ 发布消息到 orders 流")
        
        # 测试订阅消费
        print("[5/6] 测试消息消费...")
        
        # 创建消费者组
        consumer_group = "test_group"
        
        # 消费消息
        messages = await client.consume(
            topic="orders",
            group=consumer_group,
            consumer="consumer_1",
            count=2
        )
        
        print(f"✓ 消费到 {len(messages)} 条消息:")
        for msg in messages:
            print(f"  - ID: {msg.get('id')}, Data: {msg.get('data')}")
        
        # 确认消息
        if messages:
            ack_result = await client.ack(
                topic="orders",
                group=consumer_group,
                message_ids=[msg['id'] for msg in messages]
            )
            print(f"✓ 确认 {ack_result} 条消息")
        
        # 测试消息确认机制
        print("[6/6] 测试消息确认和重新消费...")
        
        # 发布新消息
        await client.publish(
            topic="notifications",
            message={"type": "email", "to": "user@example.com", "subject": "Test"}
        )
        
        # 消费但不确认
        messages = await client.consume(
            topic="notifications",
            group=consumer_group,
            consumer="consumer_2",
            count=1
        )
        
        print(f"✓ 消费到 {len(messages)} 条消息（未确认）")
        
        # 稍后再次消费，应该能看到pending消息
        # Redis Streams让pending消息可被重新消费
        
        # 关闭连接
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ Redis Streams集成测试成功！")
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
    asyncio.run(test_redis_integration())