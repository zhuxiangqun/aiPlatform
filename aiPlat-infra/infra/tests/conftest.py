"""
Pytest configuration and fixtures for infrastructure tests.
"""
import pytest
import asyncio
from typing import Generator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# PostgreSQL fixture
@pytest.fixture(scope="session")
def postgres_container() -> Generator[str, None, None]:
    """Start PostgreSQL container for testing."""
    logger.info("Setting up PostgreSQL container...")
    try:
        from testcontainers.postgres import PostgresContainer
        
        container = PostgresContainer("postgres:15-alpine")
        logger.info("Starting PostgreSQL container...")
        container.start()
        
        connection_url = container.get_connection_url()
        logger.info(f"PostgreSQL container started: {connection_url}")
        yield connection_url
        
        logger.info("Stopping PostgreSQL container...")
        container.stop()
        logger.info("PostgreSQL container stopped")
    except Exception as e:
        logger.error(f"PostgreSQL container setup failed: {e}")
        pytest.skip(f"PostgreSQL container not available: {e}")
        yield None


# MySQL fixture
@pytest.fixture(scope="session")
def mysql_container() -> Generator[str, None, None]:
    """Start MySQL container for testing."""
    logger.info("Setting up MySQL container...")
    try:
        from testcontainers.mysql import MySqlContainer
        
        container = MySqlContainer("mysql:8.0")
        logger.info("Starting MySQL container...")
        container.start()
        
        connection_url = container.get_connection_url()
        logger.info(f"MySQL container started: {connection_url}")
        yield connection_url
        
        logger.info("Stopping MySQL container...")
        container.stop()
        logger.info("MySQL container stopped")
    except Exception as e:
        logger.error(f"MySQL container setup failed: {e}")
        pytest.skip(f"MySQL container not available: {e}")
        yield None


# MongoDB fixture
@pytest.fixture(scope="session")
def mongodb_container() -> Generator[str, None, None]:
    """Start MongoDB container for testing."""
    logger.info("Setting up MongoDB container...")
    try:
        from testcontainers.mongodb import MongoDbContainer
        
        container = MongoDbContainer("mongo:7.0")
        logger.info("Starting MongoDB container...")
        container.start()
        
        # MongoDB connection URL
        connection_url = f"mongodb://{container.get_container_host_ip()}:{container.get_exposed_port(27017)}"
        logger.info(f"MongoDB container started: {connection_url}")
        yield connection_url
        
        logger.info("Stopping MongoDB container...")
        container.stop()
        logger.info("MongoDB container stopped")
    except Exception as e:
        logger.error(f"MongoDB container setup failed: {e}")
        pytest.skip(f"MongoDB container not available: {e}")
        yield None


# Redis fixture (for messaging tests)
@pytest.fixture(scope="session")
def redis_container() -> Generator[str, None, None]:
    """Start Redis container for testing."""
    logger.info("Setting up Redis container...")
    try:
        from testcontainers.redis import RedisContainer
        
        container = RedisContainer("redis:7-alpine")
        logger.info("Starting Redis container...")
        container.start()
        
        connection_url = f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}"
        logger.info(f"Redis container started: {connection_url}")
        yield connection_url
        
        logger.info("Stopping Redis container...")
        container.stop()
        logger.info("Redis container stopped")
    except Exception as e:
        logger.error(f"Redis container setup failed: {e}")
        pytest.skip(f"Redis container not available: {e}")
        yield None


# Kafka fixture (for messaging tests)
@pytest.fixture(scope="session")
def kafka_container() -> Generator[str, None, None]:
    """Start Kafka container for testing."""
    logger.info("Setting up Kafka container...")
    try:
        from testcontainers.kafka import KafkaContainer
        
        container = KafkaContainer("confluentinc/cp-kafka:7.4.0")
        logger.info("Starting Kafka container...")
        container.start()
        
        bootstrap_servers = container.get_bootstrap_server()
        logger.info(f"Kafka container started: {bootstrap_servers}")
        yield bootstrap_servers
        
        logger.info("Stopping Kafka container...")
        container.stop()
        logger.info("Kafka container stopped")
    except Exception as e:
        logger.error(f"Kafka container setup failed: {e}")
        pytest.skip(f"Kafka container not available: {e}")
        yield None


# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Pytest configuration
def pytest_collection_modifyitems(config, items):
    """Add markers to integration tests."""
    for item in items:
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)