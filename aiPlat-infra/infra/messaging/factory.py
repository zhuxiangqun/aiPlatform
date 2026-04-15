from .base import MessageClient
from .schemas import MessagingConfig


def create_messaging_client(config: MessagingConfig) -> MessageClient:
    backend = config.backend.lower()

    if backend == "kafka":
        from .kafka_backend import KafkaClient
        return KafkaClient(config)
    elif backend == "rabbitmq":
        from .rabbitmq_backend import RabbitMQClient
        return RabbitMQClient(config)
    elif backend == "redis":
        from .redis_backend import RedisClient
        return RedisClient(config)
    else:
        raise ValueError(f"Unsupported messaging backend: {backend}")
