import pytest
from infra.messaging.schemas import (
    MessagingConfig,
    KafkaOptions,
    RabbitMQOptions,
    RedisOptions,
    Message,
    Topic,
    ConsumerConfig,
)


class TestMessagingSchemas:
    def test_messaging_config_defaults(self):
        config = MessagingConfig(backend="kafka")
        assert config.backend == "kafka"
        assert config.hosts == ["localhost"]
        assert config.topic_prefix == ""
        assert config.client_id == "aiplat"

    def test_kafka_options_defaults(self):
        options = KafkaOptions()
        assert options.consumer_group == "aiplat-consumer"
        assert options.auto_offset_reset == "latest"
        assert options.enable_auto_commit is True

    def test_rabbitmq_options_defaults(self):
        options = RabbitMQOptions()
        assert options.username == "guest"
        assert options.password == "guest"
        assert options.vhost == "/"
        assert options.exchange_type == "topic"

    def test_redis_options_defaults(self):
        options = RedisOptions()
        assert options.db == 0
        assert options.password is None
        assert options.pool_size == 10

    def test_message_creation(self):
        msg = Message(
            id="test-123",
            topic="test.topic",
            body=b"test message",
            headers={"key": "value"},
        )
        assert msg.id == "test-123"
        assert msg.topic == "test.topic"
        assert msg.body == b"test message"
        assert msg.headers == {"key": "value"}

    def test_topic_creation(self):
        topic = Topic(name="test.topic", partitions=3, retention=3600)
        assert topic.name == "test.topic"
        assert topic.partitions == 3
        assert topic.retention == 3600

    def test_consumer_config_creation(self):
        config = ConsumerConfig(
            group_id="test-group",
            auto_commit=False,
            prefetch=20,
        )
        assert config.group_id == "test-group"
        assert config.auto_commit is False
        assert config.prefetch == 20


class TestMessagingFactory:
    def test_create_kafka_client(self):
        from infra.messaging.factory import create_messaging_client

        config = MessagingConfig(
            backend="kafka",
            hosts=["localhost:9092"],
            topic_prefix="test",
        )
        client = create_messaging_client(config)
        assert client is not None
        assert hasattr(client, "publish")
        assert hasattr(client, "subscribe")
        assert hasattr(client, "close")

    def test_create_rabbitmq_client(self):
        from infra.messaging.factory import create_messaging_client

        config = MessagingConfig(
            backend="rabbitmq",
            hosts=["localhost:5672"],
            rabbitmq=RabbitMQOptions(username="test", password="test"),
        )
        client = create_messaging_client(config)
        assert client is not None
        assert hasattr(client, "publish")
        assert hasattr(client, "subscribe")

    def test_create_redis_client(self):
        from infra.messaging.factory import create_messaging_client

        config = MessagingConfig(
            backend="redis",
            hosts=["localhost:6379"],
            redis=RedisOptions(db=1),
        )
        client = create_messaging_client(config)
        assert client is not None
        assert hasattr(client, "publish")
        assert hasattr(client, "subscribe")

    def test_unsupported_backend(self):
        from infra.messaging.factory import create_messaging_client

        config = MessagingConfig(backend="unsupported")
        with pytest.raises(ValueError, match="Unsupported messaging backend"):
            create_messaging_client(config)


class TestKafkaClient:
    @pytest.fixture
    def kafka_client(self):
        from infra.messaging.kafka_backend import KafkaClient

        config = MessagingConfig(
            backend="kafka",
            hosts=["localhost:9092"],
            topic_prefix="test",
        )
        return KafkaClient(config)

    def test_kafka_client_creation(self, kafka_client):
        assert kafka_client.config.backend == "kafka"
        assert kafka_client._connected is False

    def test_get_topic_name(self, kafka_client):
        topic_name = kafka_client._get_topic_name("user.created")
        assert topic_name == "test.user.created"

        kafka_client.config.topic_prefix = ""
        topic_name = kafka_client._get_topic_name("user.created")
        assert topic_name == "user.created"


class TestRabbitMQClient:
    @pytest.fixture
    def rabbitmq_client(self):
        from infra.messaging.rabbitmq_backend import RabbitMQClient

        config = MessagingConfig(
            backend="rabbitmq",
            hosts=["localhost:5672"],
            topic_prefix="test",
        )
        return RabbitMQClient(config)

    def test_rabbitmq_client_creation(self, rabbitmq_client):
        assert rabbitmq_client.config.backend == "rabbitmq"
        assert rabbitmq_client._connected is False

    def test_get_queue_name(self, rabbitmq_client):
        queue_name = rabbitmq_client._get_queue_name("user.created")
        assert queue_name == "test.user.created"

        rabbitmq_client.config.topic_prefix = ""
        queue_name = rabbitmq_client._get_queue_name("user.created")
        assert queue_name == "user.created"


class TestRedisClient:
    @pytest.fixture
    def redis_client(self):
        from infra.messaging.redis_backend import RedisClient

        config = MessagingConfig(
            backend="redis",
            hosts=["localhost:6379"],
            topic_prefix="test",
        )
        return RedisClient(config)

    def test_redis_client_creation(self, redis_client):
        assert redis_client.config.backend == "redis"
        assert redis_client._connected is False

    def test_get_channel_name(self, redis_client):
        channel_name = redis_client._get_channel_name("user.created")
        assert channel_name == "test:user.created"

        redis_client.config.topic_prefix = ""
        channel_name = redis_client._get_channel_name("user.created")
        assert channel_name == "user.created"


@pytest.mark.integration
class TestMessagingIntegration:
    @pytest.mark.asyncio
    async def test_kafka_publish_subscribe(self):
        pytest.skip("Requires running Kafka instance")

    @pytest.mark.asyncio
    async def test_rabbitmq_publish_subscribe(self):
        pytest.skip("Requires running RabbitMQ instance")

    @pytest.mark.asyncio
    async def test_redis_publish_subscribe(self):
        pytest.skip("Requires running Redis instance")