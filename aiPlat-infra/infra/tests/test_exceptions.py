"""
异常类单元测试

测试所有基础设施层异常类
"""

import pytest
from infra.exceptions import (
    InfraError,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    DatabaseQueryError,
    DatabasePoolError,
    LLMError,
    LLMConnectionError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMAuthError,
    LLMModelNotFoundError,
    VectorStoreError,
    VectorStoreConnectionError,
    VectorStoreTimeoutError,
    VectorStoreIndexError,
    VectorStoreDimensionError,
    CacheError,
    CacheConnectionError,
    CacheTimeoutError,
    CacheKeyError,
    MessagingError,
    MessagingConnectionError,
    MessagingPublishError,
    MessagingConsumeError,
    StorageError,
    StorageConnectionError,
    StorageNotFoundError,
    StoragePermissionError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigParseError,
    NetworkError,
    NetworkConnectionError,
    NetworkTimeoutError,
    ComputeError,
    ComputeResourceError,
    ComputeQuotaError,
    MemoryError,
    MemoryAllocationError,
    MemoryOOMError,
    MonitoringError,
    MetricsCollectionError,
    LoggingError,
    LogWriteError,
    DIError,
    DINavigationError,
    DIRuntimeError,
    MCPError,
    MCPConnectionError,
    MCPToolNotFoundError,
)


class TestInfraError:
    """测试基础异常类"""

    def test_infra_error_message(self):
        """测试基础异常消息"""
        error = InfraError("Test error message")
        assert str(error) == "Test error message"

    def test_infra_error_with_details(self):
        """测试带详情的异常"""
        error = InfraError("Test error", details={"key": "value"})
        assert error.message == "Test error"
        assert error.details == {"key": "value"}
        assert "key" in str(error)


class TestDatabaseErrors:
    """测试数据库异常类"""

    def test_database_connection_error(self):
        """测试数据库连接错误"""
        error = DatabaseConnectionError("postgres", "Connection refused")
        assert "postgres" in str(error)
        assert "Connection refused" in str(error)

    def test_database_timeout_error(self):
        """测试数据库超时错误"""
        error = DatabaseTimeoutError("postgres", 30.0)
        assert "postgres" in str(error)
        assert "30.0" in str(error)

    def test_database_query_error(self):
        """测试数据库查询错误"""
        error = DatabaseQueryError("Query failed", query="SELECT * FROM users")
        assert "Query failed" in str(error)
        assert error.details["query"] == "SELECT * FROM users"

    def test_database_pool_error(self):
        """测试数据库连接池错误"""
        error = DatabasePoolError("Pool exhausted", pool_stats={"active": 20, "max": 20})
        assert "Pool exhausted" in str(error)
        assert error.details["pool_stats"]["active"] == 20


class TestLLMErrors:
    """测试 LLM 异常类"""

    def test_llm_connection_error(self):
        """测试 LLM 连接错误"""
        error = LLMConnectionError("openai", "API unreachable")
        assert "openai" in str(error)
        assert "API unreachable" in str(error)

    def test_llm_timeout_error(self):
        """测试 LLM 超时错误"""
        error = LLMTimeoutError("openai", 60.0)
        assert "openai" in str(error)
        assert "60.0" in str(error)

    def test_llm_rate_limit_error(self):
        """测试 LLM 限流错误"""
        error = LLMRateLimitError("openai", retry_after=30.0)
        assert "rate limit" in str(error).lower()
        assert error.details["retry_after"] == 30.0

    def test_llm_auth_error(self):
        """测试 LLM 认证错误"""
        error = LLMAuthError("openai", "Invalid API key")
        assert "authentication" in str(error).lower()
        assert error.details["message"] == "Invalid API key"

    def test_llm_model_not_found_error(self):
        """测试模型不存在错误"""
        error = LLMModelNotFoundError("gpt-5")
        assert "gpt-5" in str(error)


class TestVectorStoreErrors:
    """测试向量存储异常类"""

    def test_vector_store_connection_error(self):
        """测试向量存储连接错误"""
        error = VectorStoreConnectionError("milvus", "Service unavailable")
        assert "milvus" in str(error)

    def test_vector_store_timeout_error(self):
        """测试向量存储超时错误"""
        error = VectorStoreTimeoutError("milvus", 30.0)
        assert "milvus" in str(error)
        assert "30.0" in str(error)

    def test_vector_store_index_error(self):
        """测试向量索引错误"""
        error = VectorStoreIndexError("embeddings", "Index not found")
        assert "embeddings" in str(error)

    def test_vector_store_dimension_error(self):
        """测试向量维度错误"""
        error = VectorStoreDimensionError(expected=1536, actual=512)
        assert "1536" in str(error)
        assert "512" in str(error)


class TestCacheErrors:
    """测试缓存异常类"""

    def test_cache_connection_error(self):
        """测试缓存连接错误"""
        error = CacheConnectionError("redis", "Connection refused")
        assert "redis" in str(error)

    def test_cache_timeout_error(self):
        """测试缓存超时错误"""
        error = CacheTimeoutError("redis", 5.0)
        assert "redis" in str(error)

    def test_cache_key_error(self):
        """测试缓存键错误"""
        error = CacheKeyError("user:123", "Key not found")
        assert "user:123" in str(error)


class TestMessagingErrors:
    """测试消息队列异常类"""

    def test_messaging_connection_error(self):
        """测试消息队列连接错误"""
        error = MessagingConnectionError("kafka", "Broker unavailable")
        assert "kafka" in str(error)

    def test_messaging_publish_error(self):
        """测试消息发布错误"""
        error = MessagingPublishError("topic-1", "Failed to publish")
        assert "topic-1" in str(error)

    def test_messaging_consume_error(self):
        """测试消息消费错误"""
        error = MessagingConsumeError("topic-1", "Failed to consume")
        assert "topic-1" in str(error)


class TestStorageErrors:
    """测试存储异常类"""

    def test_storage_connection_error(self):
        """测试存储连接错误"""
        error = StorageConnectionError("s3", "Access denied")
        assert "s3" in str(error)

    def test_storage_not_found_error(self):
        """测试资源不存在错误"""
        error = StorageNotFoundError("/path/to/file")
        assert "/path/to/file" in str(error)

    def test_storage_permission_error(self):
        """测试权限错误"""
        error = StoragePermissionError("/path/to/file", "write")
        assert "permission denied" in str(error).lower()
        assert "write" in str(error)


class TestConfigErrors:
    """测试配置异常类"""

    def test_config_not_found_error(self):
        """测试配置不存在错误"""
        error = ConfigNotFoundError("database.host")
        assert "database.host" in str(error)

    def test_config_validation_error(self):
        """测试配置验证错误"""
        error = ConfigValidationError("database.port", "invalid", "Must be integer")
        assert "database.port" in str(error)
        assert "Must be integer" in str(error)

    def test_config_parse_error(self):
        """测试配置解析错误"""
        error = ConfigParseError("config.yaml", "YAML syntax error")
        assert "config.yaml" in str(error)


class TestNetworkErrors:
    """测试网络异常类"""

    def test_network_connection_error(self):
        """测试网络连接错误"""
        error = NetworkConnectionError("localhost", 8080, "Connection refused")
        assert "localhost" in str(error)
        assert "8080" in str(error)

    def test_network_timeout_error(self):
        """测试网络超时错误"""
        error = NetworkTimeoutError("localhost", 30.0)
        assert "localhost" in str(error)
        assert "30.0" in str(error)


class TestComputeErrors:
    """测试计算资源异常类"""

    def test_compute_resource_error(self):
        """测试计算资源错误"""
        error = ComputeResourceError("gpu", requested=8, available=4)
        assert "gpu" in str(error)

    def test_compute_quota_error(self):
        """测试计算配额错误"""
        error = ComputeQuotaError("gpu", usage=8, limit=4)
        assert "gpu" in str(error)


class TestMemoryErrors:
    """测试内存异常类"""

    def test_memory_allocation_error(self):
        """测试内存分配错误"""
        error = MemoryAllocationError(size=1024, available=512)
        assert "allocation" in str(error).lower()

    def test_memory_oom_error(self):
        """测试内存溢出错误"""
        error = MemoryOOMError(usage_percent=95.0)
        assert "OOM" in str(error)


class TestMonitoringErrors:
    """测试监控异常类"""

    def test_metrics_collection_error(self):
        """测试指标收集错误"""
        error = MetricsCollectionError("cpu_usage", "Failed to collect")
        assert "cpu_usage" in str(error)


class TestLoggingErrors:
    """测试日志异常类"""

    def test_log_write_error(self):
        """测试日志写入错误"""
        error = LogWriteError("/var/log/app.log", "Permission denied")
        assert "/var/log/app.log" in str(error)


class TestDIErrors:
    """测试依赖注入异常类"""

    def test_di_registration_error(self):
        """测试 DI 注册错误"""
        error = DINavigationError("DatabaseClient", "Service not registered")
        assert "DatabaseClient" in str(error)

    def test_di_runtime_error(self):
        """测试 DI 运行时错误"""
        error = DIRuntimeError("Container disposed", details={"state": "disposed"})
        assert "Container disposed" in str(error)


class TestMCPErrors:
    """测试 MCP 异常类"""

    def test_mcp_connection_error(self):
        """测试 MCP 连接错误"""
        error = MCPConnectionError("server-1", "Connection refused")
        assert "server-1" in str(error)

    def test_mcp_tool_not_found_error(self):
        """测试 MCP 工具不存在错误"""
        error = MCPToolNotFoundError("search_tool")
        assert "search_tool" in str(error)


class TestExceptionInheritance:
    """测试异常继承关系"""

    def test_database_error_is_infra_error(self):
        """测试数据库异常继承"""
        error = DatabaseError("test")
        assert isinstance(error, InfraError)

    def test_llm_error_is_infra_error(self):
        """测试 LLM 异常继承"""
        error = LLMError("test")
        assert isinstance(error, InfraError)

    def test_vector_store_error_is_infra_error(self):
        """测试向量存储异常继承"""
        error = VectorStoreError("test")
        assert isinstance(error, InfraError)

    def test_cache_error_is_infra_error(self):
        """测试缓存异常继承"""
        error = CacheError("test")
        assert isinstance(error, InfraError)

    def test_config_error_is_infra_error(self):
        """测试配置异常继承"""
        error = ConfigError("test")
        assert isinstance(error, InfraError)


class TestExceptionRaising:
    """测试异常抛出"""

    def test_raise_database_connection_error(self):
        """测试抛出数据库连接错误"""
        with pytest.raises(DatabaseConnectionError) as exc_info:
            raise DatabaseConnectionError("postgres", "Connection failed")
        assert "postgres" in str(exc_info.value)

    def test_raise_llm_rate_limit_error(self):
        """测试抛出 LLM 限流错误"""
        with pytest.raises(LLMRateLimitError) as exc_info:
            raise LLMRateLimitError("openai", retry_after=60.0)
        assert "openai" in str(exc_info.value)
        assert exc_info.value.details["retry_after"] == 60.0

    def test_raise_config_not_found_error(self):
        """测试抛出配置不存在错误"""
        with pytest.raises(ConfigNotFoundError) as exc_info:
            raise ConfigNotFoundError("database.host")
        assert "database.host" in str(exc_info.value)

    def test_try_except_infra_error(self):
        """测试使用 InfraError 捕获所有层错误"""
        errors = [
            DatabaseError("db error"),
            LLMError("llm error"),
            VectorStoreError("vector error"),
        ]
        
        for error in errors:
            try:
                raise error
            except InfraError as e:
                assert isinstance(e, InfraError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])