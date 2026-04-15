"""
基础设施层异常定义

遵循文档中定义的错误处理规范：
- 使用自定义异常类
- 错误处理转换为层级别异常
- 禁止暴露底层异常到上层
"""

from typing import Any, Optional


class InfraError(Exception):
    """基础设施层基础异常"""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


# ============================================================
# 数据库异常
# ============================================================

class DatabaseError(InfraError):
    """数据库基础异常"""
    pass


class DatabaseConnectionError(DatabaseError):
    """数据库连接错误"""
    
    def __init__(self, database: str, message: str):
        super().__init__(
            f"Database connection error: {database}",
            {"database": database, "message": message}
        )


class DatabaseTimeoutError(DatabaseError):
    """数据库超时错误"""
    
    def __init__(self, database: str, timeout: float):
        super().__init__(
            f"Database timeout: {database}",
            {"database": database, "timeout": timeout}
        )


class DatabaseQueryError(DatabaseError):
    """数据库查询错误"""
    
    def __init__(self, message: str, query: Optional[str] = None):
        super().__init__(
            message,
            {"query": query} if query else {}
        )


class DatabasePoolError(DatabaseError):
    """数据库连接池错误"""
    
    def __init__(self, message: str, pool_stats: Optional[dict] = None):
        super().__init__(
            message,
            {"pool_stats": pool_stats} if pool_stats else {}
        )


# ============================================================
# LLM 异常
# ============================================================

class LLMError(InfraError):
    """LLM 基础异常"""
    pass


class LLMConnectionError(LLMError):
    """LLM 连接错误"""
    
    def __init__(self, provider: str, message: str):
        super().__init__(
            f"LLM connection error: {provider}",
            {"provider": provider, "message": message}
        )


class LLMTimeoutError(LLMError):
    """LLM 超时错误"""
    
    def __init__(self, provider: str, timeout: float):
        super().__init__(
            f"LLM timeout: {provider}",
            {"provider": provider, "timeout": timeout}
        )


class LLMRateLimitError(LLMError):
    """LLM 限流错误"""
    
    def __init__(self, provider: str, retry_after: Optional[float] = None):
        super().__init__(
            f"LLM rate limit exceeded: {provider}",
            {"provider": provider, "retry_after": retry_after}
        )


class LLMAuthError(LLMError):
    """LLM 认证错误"""
    
    def __init__(self, provider: str, message: str = "Authentication failed"):
        super().__init__(
            f"LLM authentication error: {provider}",
            {"provider": provider, "message": message}
        )


class LLMModelNotFoundError(LLMError):
    """LLM 模型不存在错误"""
    
    def __init__(self, model: str):
        super().__init__(
            f"Model not found: {model}",
            {"model": model}
        )


# ============================================================
# 向量存储异常
# ============================================================

class VectorStoreError(InfraError):
    """向量存储基础异常"""
    pass


class VectorStoreConnectionError(VectorStoreError):
    """向量存储连接错误"""
    
    def __init__(self, backend: str, message: str):
        super().__init__(
            f"Vector store connection error: {backend}",
            {"backend": backend, "message": message}
        )


class VectorStoreTimeoutError(VectorStoreError):
    """向量存储超时错误"""
    
    def __init__(self, backend: str, timeout: float):
        super().__init__(
            f"Vector store timeout: {backend}",
            {"backend": backend, "timeout": timeout}
        )


class VectorStoreIndexError(VectorStoreError):
    """向量存储索引错误"""
    
    def __init__(self, index_name: str, message: str):
        super().__init__(
            f"Vector store index error: {index_name}",
            {"index_name": index_name, "message": message}
        )


class VectorStoreDimensionError(VectorStoreError):
    """向量维度不匹配错误"""
    
    def __init__(self, expected: int, actual: int):
        super().__init__(
            f"Dimension mismatch: expected {expected}, got {actual}",
            {"expected": expected, "actual": actual}
        )


# ============================================================
# 缓存异常
# ============================================================

class CacheError(InfraError):
    """缓存基础异常"""
    pass


class CacheConnectionError(CacheError):
    """缓存连接错误"""
    
    def __init__(self, backend: str, message: str):
        super().__init__(
            f"Cache connection error: {backend}",
            {"backend": backend, "message": message}
        )


class CacheTimeoutError(CacheError):
    """缓存超时错误"""
    
    def __init__(self, backend: str, timeout: float):
        super().__init__(
            f"Cache timeout: {backend}",
            {"backend": backend, "timeout": timeout}
        )


class CacheKeyError(CacheError):
    """缓存键错误"""
    
    def __init__(self, key: str, message: str = "Key not found"):
        super().__init__(
            f"Cache key error: {key}",
            {"key": key, "message": message}
        )


# ============================================================
# 消息队列异常
# ============================================================

class MessagingError(InfraError):
    """消息队列基础异常"""
    pass


class MessagingConnectionError(MessagingError):
    """消息队列连接错误"""
    
    def __init__(self, backend: str, message: str):
        super().__init__(
            f"Messaging connection error: {backend}",
            {"backend": backend, "message": message}
        )


class MessagingPublishError(MessagingError):
    """消息发布错误"""
    
    def __init__(self, topic: str, message: str):
        super().__init__(
            f"Failed to publish message to topic: {topic}",
            {"topic": topic, "message": message}
        )


class MessagingConsumeError(MessagingError):
    """消息消费错误"""
    
    def __init__(self, topic: str, message: str):
        super().__init__(
            f"Failed to consume message from topic: {topic}",
            {"topic": topic, "message": message}
        )


# ============================================================
# 存储异常
# ============================================================

class StorageError(InfraError):
    """存储基础异常"""
    pass


class StorageConnectionError(StorageError):
    """存储连接错误"""
    
    def __init__(self, backend: str, message: str):
        super().__init__(
            f"Storage connection error: {backend}",
            {"backend": backend, "message": message}
        )


class StorageNotFoundError(StorageError):
    """存储资源不存在错误"""
    
    def __init__(self, path: str):
        super().__init__(
            f"Storage resource not found: {path}",
            {"path": path}
        )


class StoragePermissionError(StorageError):
    """存储权限错误"""
    
    def __init__(self, path: str, operation: str):
        super().__init__(
            f"Storage permission denied: {operation} on {path}",
            {"path": path, "operation": operation}
        )


# ============================================================
# 配置异常
# ============================================================

class ConfigError(InfraError):
    """配置基础异常"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置不存在错误"""
    
    def __init__(self, key: str):
        super().__init__(
            f"Config not found: {key}",
            {"key": key}
        )


class ConfigValidationError(ConfigError):
    """配置验证错误"""
    
    def __init__(self, key: str, value: Any, reason: str):
        super().__init__(
            f"Config validation failed: {key}",
            {"key": key, "value": str(value), "reason": reason}
        )


class ConfigParseError(ConfigError):
    """配置解析错误"""
    
    def __init__(self, source: str, message: str):
        super().__init__(
            f"Failed to parse config from {source}",
            {"source": source, "message": message}
        )


# ============================================================
# 网络异常
# ============================================================

class NetworkError(InfraError):
    """网络基础异常"""
    pass


class NetworkConnectionError(NetworkError):
    """网络连接错误"""
    
    def __init__(self, host: str, port: int, message: str):
        super().__init__(
            f"Network connection error: {host}:{port}",
            {"host": host, "port": port, "message": message}
        )


class NetworkTimeoutError(NetworkError):
    """网络超时错误"""
    
    def __init__(self, host: str, timeout: float):
        super().__init__(
            f"Network timeout: {host}",
            {"host": host, "timeout": timeout}
        )


# ============================================================
# 计算资源异常
# ============================================================

class ComputeError(InfraError):
    """计算资源基础异常"""
    pass


class ComputeResourceError(ComputeError):
    """计算资源不足错误"""
    
    def __init__(self, resource_type: str, requested: Any, available: Any):
        super().__init__(
            f"Insufficient compute resource: {resource_type}",
            {"type": resource_type, "requested": str(requested), "available": str(available)}
        )


class ComputeQuotaError(ComputeError):
    """计算配额超限错误"""
    
    def __init__(self, quota: str, usage: Any, limit: Any):
        super().__init__(
            f"Compute quota exceeded: {quota}",
            {"quota": quota, "usage": str(usage), "limit": str(limit)}
        )


# ============================================================
# 内存异常
# ============================================================

class MemoryError(InfraError):
    """内存基础异常"""
    pass


class MemoryAllocationError(MemoryError):
    """内存分配错误"""
    
    def __init__(self, size: int, available: int):
        super().__init__(
            f"Memory allocation failed",
            {"requested_size": size, "available": available}
        )


class MemoryOOMError(MemoryError):
    """内存溢出错误"""
    
    def __init__(self, usage_percent: float):
        super().__init__(
            f"Memory OOM protection triggered",
            {"usage_percent": usage_percent}
        )


# ============================================================
# 监控异常
# ============================================================

class MonitoringError(InfraError):
    """监控基础异常"""
    pass


class MetricsCollectionError(MonitoringError):
    """指标收集错误"""
    
    def __init__(self, metric_name: str, message: str):
        super().__init__(
            f"Failed to collect metric: {metric_name}",
            {"metric_name": metric_name, "message": message}
        )


# ============================================================
# 日志异常
# ============================================================

class LoggingError(InfraError):
    """日志基础异常"""
    pass


class LogWriteError(LoggingError):
    """日志写入错误"""
    
    def __init__(self, path: str, message: str):
        super().__init__(
            f"Failed to write log: {path}",
            {"path": path, "message": message}
        )


# ============================================================
# 依赖注入异常
# ============================================================

class DIError(InfraError):
    """依赖注入基础异常"""
    pass


class DINavigationError(DIError):
    """DI 注册错误"""
    
    def __init__(self, service_name: str, message: str):
        super().__init__(
            f"Service registration error: {service_name}",
            {"service_name": service_name, "message": message}
        )


class DIRuntimeError(DIError):
    """DI 运行时错误"""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(f"DI runtime error: {message}", details)


# ============================================================
# MCP 异常
# ============================================================

class MCPError(InfraError):
    """MCP 基础异常"""
    pass


class MCPConnectionError(MCPError):
    """MCP 连接错误"""
    
    def __init__(self, server_name: str, message: str):
        super().__init__(
            f"MCP connection error: {server_name}",
            {"server_name": server_name, "message": message}
        )


class MCPToolNotFoundError(MCPError):
    """MCP 工具不存在错误"""
    
    def __init__(self, tool_name: str):
        super().__init__(
            f"MCP tool not found: {tool_name}",
            {"tool_name": tool_name}
        )