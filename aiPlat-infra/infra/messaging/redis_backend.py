import asyncio
import json
import uuid
from typing import Callable, Dict, Optional
from datetime import datetime

from .base import MessageClient
from .schemas import Message, ConsumerConfig, MessagingConfig


class RedisClient(MessageClient):
    def __init__(self, config: MessagingConfig):
        self.config = config
        self._redis = None
        self._connected = False
        self._handlers: Dict[str, Callable] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._consumer_groups: Dict[str, str] = {}
        self._pending_messages: Dict[str, tuple] = {}

    async def _connect(self):
        if self._connected:
            return

        try:
            import redis.asyncio as redis

            redis_options = self.config.redis or {}
            
            # 兼容RedisOptions对象和字典
            if hasattr(redis_options, 'db'):
                db = redis_options.db
                password = redis_options.password
            elif isinstance(redis_options, dict):
                db = redis_options.get('db', 0)
                password = redis_options.get('password')
            else:
                db = 0
                password = None
            
            host_port = self.config.hosts[0] if self.config.hosts else "localhost"
            if ":" in host_port:
                host, port_str = host_port.split(":", 1)
                port = int(port_str)
            else:
                host = host_port
                port = 6379

            self._redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,
            )
            
            await self._redis.ping()
            self._connected = True

        except ImportError:
            raise RuntimeError(
                "redis not installed. Install with: pip install redis"
            )

    def _get_channel_name(self, topic: str) -> str:
        if self.config.topic_prefix:
            return f"{self.config.topic_prefix}:{topic}"
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

        stream_name = self._get_channel_name(topic)
        headers = kwargs.get("headers", {})
        message_id = kwargs.get("message_id", str(uuid.uuid4()))

        message_data = {
            "id": message_id,
            "body": message.decode() if isinstance(message, bytes) else message,
            "headers": json.dumps(headers),
            "timestamp": datetime.now().isoformat(),
        }

        await self._redis.xadd(stream_name, message_data)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        config: Optional[ConsumerConfig] = None,
    ) -> None:
        await self._connect()

        stream_name = self._get_channel_name(topic)
        self._handlers[stream_name] = handler
        
        consumer_group = config.group_id if config else "aiplat-consumer"
        self._consumer_groups[stream_name] = consumer_group
        
        try:
            await self._redis.xgroup_create(stream_name, consumer_group, id="0", mkstream=True)
        except Exception:
            pass

        if not self._running:
            self._running = True
            task = asyncio.create_task(self._consume_stream_messages(stream_name, config))
            self._running_tasks[stream_name] = task

    async def _consume_stream_messages(self, stream_name: str, config: Optional[ConsumerConfig] = None):
        consumer_group = self._consumer_groups.get(stream_name, "aiplat-consumer")
        consumer_name = f"{consumer_group}-{uuid.uuid4().hex[:8]}"
        handler = self._handlers.get(stream_name)
        
        if not handler:
            return
        
        try:
            while self._running:
                try:
                    messages = await self._redis.xreadgroup(
                        groupname=consumer_group,
                        consumername=consumer_name,
                        streams={stream_name: ">"},
                        count=1,
                        block=1000
                    )
                    
                    if messages:
                        for stream, msg_list in messages:
                            for msg_id, msg_data in msg_list:
                                try:
                                    msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                                    
                                    body = msg_data.get(b"body", msg_data.get("body", b""))
                                    if isinstance(body, str):
                                        body = body.encode()
                                    
                                    headers_str = msg_data.get(b"headers", msg_data.get("headers", "{}"))
                                    if isinstance(headers_str, bytes):
                                        headers_str = headers_str.decode()
                                    headers = json.loads(headers_str) if headers_str else {}
                                    
                                    custom_id = msg_data.get(b"id", msg_data.get("id", msg_id_str))
                                    if isinstance(custom_id, bytes):
                                        custom_id = custom_id.decode()
                                    
                                    msg_obj = self._create_message(
                                        msg_id=custom_id,
                                        topic=stream_name,
                                        body=body,
                                        headers=headers,
                                    )
                                    
                                    msg_obj.metadata["redis_stream_id"] = msg_id_str
                                    self._pending_messages[custom_id] = (stream_name, msg_id_str)
                                    
                                    await handler(msg_obj)
                                    
                                    if config and config.auto_commit:
                                        await self.ack(custom_id)
                                    
                                except Exception as e:
                                    print(f"Error processing message: {e}")
                                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"Error in stream consumer: {e}")
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            pass

    async def unsubscribe(self, topic: str) -> None:
        stream_name = self._get_channel_name(topic)

        if stream_name in self._handlers:
            del self._handlers[stream_name]

        if stream_name in self._running_tasks:
            task = self._running_tasks.pop(stream_name)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if stream_name in self._consumer_groups:
            del self._consumer_groups[stream_name]

    async def ack(self, message_id: str) -> None:
        if message_id not in self._pending_messages:
            return
        
        stream_name, redis_stream_id = self._pending_messages.pop(message_id)
        
        try:
            await self._redis.xack(stream_name, self._consumer_groups.get(stream_name, "aiplat-consumer"), redis_stream_id)
        except Exception as e:
            print(f"Error acknowledging message: {e}")

    async def nack(self, message_id: str) -> None:
        if message_id not in self._pending_messages:
            return
        
        stream_name, redis_stream_id = self._pending_messages.pop(message_id)
        
        try:
            await self._redis.xdel(stream_name, redis_stream_id)
        except Exception as e:
            print(f"Error nacking message: {e}")

    async def close(self) -> None:
        self._running = False

        for task in list(self._running_tasks.values()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._running_tasks.clear()
        
        if self._redis:
            await self._redis.close()
            self._redis = None

        self._connected = False