from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    id: str
    topic: str
    body: bytes
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Topic:
    name: str
    partitions: int = 1
    retention: int = 86400


@dataclass
class ConsumerConfig:
    group_id: str
    auto_commit: bool = True
    prefetch: int = 10
    auto_offset_reset: str = "latest"


@dataclass
class ProducerConfig:
    acks: str = "all"
    retries: int = 3
    batch_size: int = 16384
    linger_ms: int = 0


@dataclass
class KafkaOptions:
    consumer_group: str = "aiplat-consumer"
    auto_offset_reset: str = "latest"
    enable_auto_commit: bool = True
    session_timeout_ms: int = 10000
    heartbeat_interval_ms: int = 3000


@dataclass
class RabbitMQOptions:
    username: str = "guest"
    password: str = "guest"
    vhost: str = "/"
    exchange_type: str = "topic"
    durable: bool = True


@dataclass
class RedisOptions:
    db: int = 0
    password: Optional[str] = None
    pool_size: int = 10


@dataclass
class MessagingConfig:
    backend: str
    hosts: List[str] = field(default_factory=lambda: ["localhost"])
    topic_prefix: str = ""
    client_id: str = "aiplat"
    kafka: Optional[KafkaOptions] = None
    rabbitmq: Optional[RabbitMQOptions] = None
    redis: Optional[RedisOptions] = None
    options: Dict[str, Any] = field(default_factory=dict)