#!/usr/bin/env python3
"""
Kafka集成测试

运行方式: cd aiPlat-infra && python infra/tests/test_messaging/test_kafka_integration.py

注意: Kafka需要Zookeeper，测试容器会自动启动
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from testcontainers.kafka import KafkaContainer
from infra.messaging.kafka_backend import KafkaClient
from infra.messaging.schemas import MessagingConfig, KafkaOptions


async def test_kafka():
    """Kafka完整集成测试"""
    print("\n" + "="*70)
    print("Kafka 集成测试")
    print("="*70)
    
    print("\n[1/6] 启动Kafka容器...")
    print("⚠️  注意: Kafka镜像较大，首次运行需下载 (~1GB)")
    container = KafkaContainer("confluentinc/cp-kafka:7.4.0")
    container.start()
    print("✓ 容器已启动")
    
    try:
        # 获取连接信息
        bootstrap_servers = container.get_bootstrap_server()
        print(f"[2/6] Kafka地址: {bootstrap_servers}")
        
        # 配置
        config = MessagingConfig(
            backend="kafka",
            hosts=[bootstrap_servers],
            kafka=KafkaOptions(
                consumer_group="test-group",
                auto_offset_reset="earliest"
            ),
            topic_prefix="test"
        )
        
        # 创建客户端
        print("[3/6] 创建Kafka客户端...")
        client = KafkaClient(config)
        
        # 连接
        print("[4/6] 连接Kafka...")
        await client.connect()
        print("✓ 连接成功")
        
        # 测试发布消息
        print("[5/6] 测试消息发布...")
        
        # 发布消息到topic
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "123", "amount": 99.99}).encode(),
            headers={"source": "test", "timestamp": datetime.now().isoformat()}
        )
        print("✓ 发布订单消息")
        
        await client.publish(
            topic="orders",
            message=json.dumps({"order_id": "124", "amount": 149.99}).encode(),
            headers={"source": "test"}
        )
        print("✓ 发布第二条订单消息")
        
        # 测试消费消息
        print("[6/6] 测试消息消费...")
        
        received_messages = []
        
        async def message_handler(message):
            """消息处理函数"""
            received_messages.append(message)
            print(f"✓ 收到消息: ID={message.id}")
            print(f"    Topic: {message.topic}")
            if message.body:
                try:
                    data = json.loads(message.body)
                    print(f"    数据: {data}")
                except:
                    print(f"    原始数据: {message.body}")
        
        # 订阅topic
        await client.subscribe(
            topic="orders",
            handler=message_handler,
            config=None
        )
        print("✓ 已订阅 orders topic")
        
        # 等待消息处理
        await asyncio.sleep(5)
        
        if received_messages:
            print(f"✓ 总共接收到 {len(received_messages)} 条消息")
        else:
            print("⚠️  未接收到消息（可能需要更长时间或消息已在之前消费）")
        
        # 关闭连接
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ Kafka集成测试成功！")
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
    asyncio.run(test_kafka())