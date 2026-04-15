import asyncio
import uuid
from typing import Callable, Dict, Optional
from datetime import datetime

from .base import MessageClient
from .schemas import Message, ConsumerConfig, MessagingConfig


class KafkaClient(MessageClient):
    def __init__(self, config: MessagingConfig):
        self.config = config
        self._producer = None
        self._consumers: Dict[str, any] = {}
        self._connected = False
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._message_offsets: Dict[str, tuple] = {}

    async def _connect(self):
        if self._connected:
            return

        try:
            from aiokafka import AioKafkaProducer

            kafka_options = self.config.kafka or {}
            producer_config = {
                "bootstrap_servers": self.config.hosts,
                "client_id": self.config.client_id,
            }
            
            if kafka_options.acks != "all":
                producer_config["acks"] = kafka_options.acks

            self._producer = AioKafkaProducer(**producer_config)
            await self._producer.start()
            self._connected = True

        except ImportError:
            raise RuntimeError(
                "aiokafka not installed. Install with: pip install aiokafka"
            )

    async def _ensure_topic(self, topic: str):
        topic_name = self._get_topic_name(topic)
        
        try:
            from aiokafka import AioKafkaAdminClient
            
            admin = AioKafkaAdminClient(bootstrap_servers=self.config.hosts)
            await admin.start()
            
            try:
                topics = await admin.list_topics()
                if topic_name not in topics:
                    from aiokafka.admin import NewTopic
                    
                    new_topic = NewTopic(
                        name=topic_name,
                        num_partitions=getattr(self.config.kafka, ConsumerConfig).group_id if self.config.kafka else 1,
                        replication_factor=1
                    )
                    await admin.create_topics([new_topic])
            finally:
                await admin.close()
        except Exception:
            pass

    def _get_topic_name(self, topic: str) -> str:
        if self.config.topic_prefix:
            return f"{self.config.topic_prefix}.{topic}"
        return topic

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

        topic_name = self._get_topic_name(topic)
        headers = kwargs.get("headers", {})
        key = kwargs.get("key")
        partition = kwargs.get("partition")

        kafka_headers = [(k, v.encode() if isinstance(v, str) else v) for k, v in headers.items()]

        await self._producer.send_and_wait(
            topic_name, message, key=key, partition=partition, headers=kafka_headers
        )

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        config: Optional[ConsumerConfig] = None,
    ) -> None:
        await self._connect()

        topic_name = self._get_topic_name(topic)
        self._handlers[topic_name] = handler

        if topic_name in self._consumers:
            return

        try:
            from aiokafka import AioKafkaConsumer

            kafka_options = self.config.kafka or {}
            consumer_group = config.group_id if config else kafka_options.consumer_group
            auto_offset_reset = config.auto_offset_reset if config else kafka_options.auto_offset_reset
            enable_auto_commit = config.auto_commit if config else kafka_options.enable_auto_commit

            consumer_config = {
                "group_id": consumer_group,
                "bootstrap_servers": self.config.hosts,
                "client_id": self.config.client_id,
                "auto_offset_reset": auto_offset_reset,
                "enable_auto_commit": enable_auto_commit,
            }

            consumer = AioKafkaConsumer(topic_name, **consumer_config)
            await consumer.start()
            self._consumers[topic_name] = consumer

            if not self._running:
                self._running = True
                asyncio.create_task(self._consume_messages(topic_name))

        except ImportError:
            raise RuntimeError(
                "aiokafka not installed. Install with: pip install aiokafka"
            )

    async def _consume_messages(self, topic: str):
        consumer = self._consumers.get(topic)
        handler = self._handlers.get(topic)

        if not consumer or not handler:
            return

        try:
            async for msg in consumer:
                try:
                    msg_id = str(uuid.uuid4())
                    message = self._create_message(
                        msg_id=msg_id,
                        topic=topic,
                        body=msg.value,
                        headers={k: v.decode() if v else "" for k, v in (msg.headers or [])},
                    )
                    message.metadata["offset"] = msg.offset
                    message.metadata["partition"] = msg.partition
                    
                    self._message_offsets[msg_id] = (topic, msg.partition, msg.offset)

                    await handler(message)

                except Exception as e:
                    print(f"Error processing message: {e}")

        except asyncio.CancelledError:
            pass

    async def unsubscribe(self, topic: str) -> None:
        topic_name = self._get_topic_name(topic)

        if topic_name in self._consumers:
            consumer = self._consumers.pop(topic_name)
            await consumer.stop()

        if topic_name in self._handlers:
            del self._handlers[topic_name]

    async def ack(self, message_id: str) -> None:
        if message_id not in self._message_offsets:
            return
        
        offset_info = self._message_offsets.pop(message_id, None)
        if not offset_info:
            return
        
        topic, partition, offset = offset_info
        consumer = self._consumers.get(topic)
        
        if not consumer:
            return
        
        try:
            kafka_options = self.config.kafka or {}
            enable_auto_commit = kafka_options.enable_auto_commit
            
            if not enable_auto_commit:
                from aiokafka import TopicPartition
                tp = TopicPartition(topic, partition)
                await consumer.commit({tp: offset + 1})
        except Exception as e:
            print(f"Error committing offset: {e}")

    async def nack(self, message_id: str) -> None:
        if message_id in self._message_offsets:
            del self._message_offsets[message_id]

    async def close(self) -> None:
        self._running = False

        for topic, consumer in list(self._consumers.items()):
            try:
                await consumer.stop()
            except Exception:
                pass
        self._consumers.clear()

        if self._producer:
            await self._producer.stop()
            self._producer = None

        self._connected = False