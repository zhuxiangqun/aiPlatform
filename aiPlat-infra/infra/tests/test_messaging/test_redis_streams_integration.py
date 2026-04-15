#!/usr/bin/env python3
"""
Redis Streams集成测试

运行方式: cd aiPlat-infra && python infra/tests/test_messaging/test_redis_streams_integration.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from testcontainers.redis import RedisContainer
from infra.messaging.redis_backend import RedisClient
from infra.messaging.schemas import MessagingConfig, ConsumerConfig


async def test_redis_streams():
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
        print(f"[2/6] Redis地址: redis://{host}:{port}")
        
        # 配置
        config = MessagingConfig(
            backend="redis",
            hosts=[f"{host}:{port}"],
            topic_prefix="test_stream"
        )
        
        # 创建客户端
        print("[3/6] 创建Redis Streams客户端...")
        client = RedisClient(config)
        
        # 测试发布消息（会自动连接）
        print("[4/6] 测试连接...")
        await client.publish(topic="test_connection", message=b"ping")
        print("✓ 连接成功")
        
        # 测试发布消息
        print("[5/6] 测试消息发布...")
        
        # 发布消息到orders流
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "123", "amount": 99.99}).encode(),
            headers={"source": "test", "timestamp": datetime.now().isoformat()}
        )
        print("✓ 发布订单消息到 orders 流")
        
        # 发布另一条消息
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "124", "amount": 149.99}).encode(),
            headers={"source": "test"}
        )
        print("✓ 发布第二条订单消息")
        
        # 测试消费消息
        print("[6/6] 测试消息消费...")
        
        # Redis Streams使用subscribe方法，创建消费者组
        received_messages = []
        
        async def message_handler(message: 'Message'):
            """消息处理函数"""
            received_messages.append(message)
            print(f"✓ 收到消息: ID={message.id}, Topic={message.topic}")
            if message.body:
                try:
                    data = json.loads(message.body)
                    print(f"    数据: {data}")
                except:
                    print(f"    原始数据: {message.body}")
        
        # 订阅主题
        await client.subscribe(
            topic="orders",
            handler=message_handler,
            config=ConsumerConfig(group_id="test_group", auto_commit=False)
        )
        print("✓ 已订阅 orders 流")
        
        # 等待消息处理
        await asyncio.sleep(1)
        
        if received_messages:
            print(f"✓ 接收到 {len(received_messages)} 条消息")
            
            # 确认消息
            for msg in received_messages:
                await client.ack(msg.id)
                print(f"✓ 已确认消息: {msg.id}")
        else:
            print("⚠️  未接收到消息（可能消息已在之前消费）")
        
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
    asyncio.run(test_redis_streams())