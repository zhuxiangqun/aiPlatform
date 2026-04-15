import asyncio
import uuid
from typing import Callable, Dict, Optional
from datetime import datetime

from .base import MessageClient
from .schemas import Message, ConsumerConfig, MessagingConfig


class RabbitMQClient(MessageClient):
    def __init__(self, config: MessagingConfig):
        self.config = config
        self._connection = None
        self._channel = None
        self._connected = False
        self._consumers: Dict[str, str] = {}
        self._handlers: Dict[str, Callable] = {}
        self._queues: Dict[str, any] = {}
        self._pending_messages: Dict[str, any] = {}
        self._running = False

    async def _connect(self):
        if self._connected:
            return

        try:
            import aio_pika

            rabbitmq_options = self.config.rabbitmq or {}
            host = self.config.hosts[0] if self.config.hosts else "localhost"
            
            if ":" in host:
                host_part, port_part = host.split(":", 1)
                port = int(port_part)
            else:
                host_part = host
                port = 5672

            self._connection = await aio_pika.connect_robust(
                host=host_part,
                port=port,
                login=rabbitmq_options.username,
                password=rabbitmq_options.password,
                virtualhost=rabbitmq_options.vhost,
            )

            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=10)
            
            self._connected = True

        except ImportError:
            raise RuntimeError(
                "aio_pika not installed. Install with: pip install aio-pika"
            )

    def _get_queue_name(self, topic: str) -> str:
        if self.config.topic_prefix:
            return f"{self.config.topic_prefix}.{topic}"
        return topic

    def _get_exchange_name(self, topic: str) -> str:
        if self.config.topic_prefix:
            return f"{self.config.topic_prefix}.exchange"
        return "messaging.exchange"

    def _create_message(
        self, msg_id: str, topic: str, body: bytes, headers: Dict[str, str] = None
    ) -> Message:
        return Message(
            id=msg_id,
            topic=topic,
            body=body,
            headers=headers or {},
            timestamp=datetime.now(),
        )

    async def publish(self, topic: str, message: bytes, **kwargs) -> None:
        await self._connect()

        import aio_pika

        exchange_name = self._get_exchange_name(topic)
        routing_key = self._get_queue_name(topic)
        
        headers = kwargs.get("headers", {})
        message_id = kwargs.get("message_id", str(uuid.uuid4()))
        
        rabbitmq_options = self.config.rabbitmq or {}
        exchange_type = rabbitmq_options.exchange_type

        exchange = await self._channel.declare_exchange(
            exchange_name, aio_pika.ExchangeType(exchange_type), durable=rabbitmq_options.durable
        )

        message_obj = aio_pika.Message(
            body=message,
            headers=headers,
            message_id=message_id,
            content_type=kwargs.get("content_type", "application/octet-stream"),
        )

        await exchange.publish(message_obj, routing_key=routing_key)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        config: Optional[ConsumerConfig] = None,
    ) -> None:
        await self._connect()

        import aio_pika

        queue_name = self._get_queue_name(topic)
        exchange_name = self._get_exchange_name(topic)
        
        self._handlers[queue_name] = handler
        
        rabbitmq_options = self.config.rabbitmq or {}
        exchange_type = rabbitmq_options.exchange_type

        exchange = await self._channel.declare_exchange(
            exchange_name, aio_pika.ExchangeType(exchange_type), durable=rabbitmq_options.durable
        )

        queue = await self._channel.declare_queue(queue_name, durable=rabbitmq_options.durable)
        await queue.bind(exchange, routing_key=queue_name)
        
        self._queues[queue_name] = queue

        if config and config.prefetch > 0:
            await self._channel.set_qos(prefetch_count=config.prefetch)

        async def process_message(message: aio_pika.IncomingMessage):
            try:
                msg_id = message.message_id or str(uuid.uuid4())
                msg_obj = self._create_message(
                    msg_id=msg_id,
                    topic=topic,
                    body=message.body,
                    headers=dict(message.headers or {}),
                )
                
                self._pending_messages[msg_id] = message
                
                if handler:
                    await handler(msg_obj)
                
                if config and config.auto_commit:
                    await self.ack(msg_id)

            except Exception as e:
                print(f"Error processing message: {e}")
                if message.message_id:
                    await self.nack(message.message_id)

        await queue.consume(process_message)
        self._running = True

    async def unsubscribe(self, topic: str) -> None:
        queue_name = self._get_queue_name(topic)
        
        if queue_name in self._handlers:
            del self._handlers[queue_name]
        
        if queue_name in self._queues:
            del self._queues[queue_name]

    async def ack(self, message_id: str) -> None:
        if message_id not in self._pending_messages:
            return
        
        message = self._pending_messages.pop(message_id)
        
        try:
            await message.ack()
        except Exception as e:
            print(f"Error acknowledging message: {e}")

    async def nack(self, message_id: str) -> None:
        if message_id not in self._pending_messages:
            return
        
        message = self._pending_messages.pop(message_id)
        
        try:
            await message.nack(requeue=True)
        except Exception as e:
            print(f"Error nacking message: {e}")

    async def close(self) -> None:
        self._running = False
        
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            
        self._connected = False