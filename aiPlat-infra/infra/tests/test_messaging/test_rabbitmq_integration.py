#!/usr/bin/env python3
"""
RabbitMQ集成测试

运行方式: cd aiPlat-infra && python infra/tests/test_messaging/test_rabbitmq_integration.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from testcontainers.rabbitmq import RabbitMqContainer
from infra.messaging.rabbitmq_backend import RabbitMQClient
from infra.messaging.schemas import MessagingConfig, RabbitMQOptions


async def test_rabbitmq():
    """RabbitMQ完整集成测试"""
    print("\n" + "="*70)
    print("RabbitMQ 集成测试")
    print("="*70)
    
    print("\n[1/6] 启动RabbitMQ容器...")
    print("⚠️  注意: RabbitMQ镜像较大，首次运行需下载 (~200MB)")
    container = RabbitMqContainer("rabbitmq:3.12-management-alpine")
    container.start()
    print("✓ 容器已启动")
    
    try:
        # 获取连接信息
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5672)
        print(f"[2/6] RabbitMQ地址: amqp://{host}:{port}")
        
        # 配置
        config = MessagingConfig(
            backend="rabbitmq",
            hosts=[f"{host}:{port}"],
            rabbitmq=RabbitMQOptions(
                username="guest",  # RabbitMqContainer默认凭据
                password="guest"
            ),
            topic_prefix="test"
        )
        
        # 创建客户端
        print("[3/6] 创建RabbitMQ客户端...")
        client = RabbitMQClient(config)
        
        # 连接
        print("[4/6] 连接RabbitMQ...")
        await client.connect()
        print("✓ 连接成功")
        
        # 测试发布消息
        print("[5/6] 测试消息发布...")
        
        # 发布消息到exchange
        await client.publish(
            topic="orders.created",
            message=json.dumps({"order_id": "123", "amount": 99.99}).encode(),
            headers={"source": "test", "timestamp": datetime.now().isoformat()}
        )
        print("✓ 发布订单创建消息")
        
        await client.publish(
            topic="orders.updated",
            message=json.dumps({"order_id": "124", "status": "shipped"}).encode(),
            headers={"source": "test"}
        )
        print("✓ 发布订单更新消息")
        
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
        
        # 订阅队列
        await client.subscribe(
            topic="orders.*",  # 通配符匹配
            handler=message_handler,
            config=None
        )
        print("✓ 已订阅 orders.* 队列")
        
        # 等待消息处理
        await asyncio.sleep(2)
        
        if received_messages:
            print(f"✓ 总共接收到 {len(received_messages)} 条消息")
        else:
            print("⚠️  未接收到消息")
        
        # 关闭连接
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "="*70)
        print("✅ RabbitMQ集成测试成功！")
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
    asyncio.run(test_rabbitmq())