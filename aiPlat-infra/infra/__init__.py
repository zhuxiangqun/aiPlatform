"""
AI Platform - Infrastructure Layer
"""

import sys

# 确保标准库 logging 先被加载
import logging

# 把标准库 logging 放入 sys.modules 的顶层，防止被覆盖
sys.modules["logging"] = logging
sys.modules["getLogger"] = logging.getLogger
sys.modules["Logger"] = logging.Logger

__version__ = "1.0.0"

# 导出异常类
from .exceptions import (
    InfraError,
    # 数据库异常
    DatabaseError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    DatabaseQueryError,
    DatabasePoolError,
    # LLM 异常
    LLMError,
    LLMConnectionError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMAuthError,
    LLMModelNotFoundError,
    # 向量存储异常
    VectorStoreError,
    VectorStoreConnectionError,
    VectorStoreTimeoutError,
    VectorStoreIndexError,
    VectorStoreDimensionError,
    # 缓存异常
    CacheError,
    CacheConnectionError,
    CacheTimeoutError,
    CacheKeyError,
    # 消息队列异常
    MessagingError,
    MessagingConnectionError,
    MessagingPublishError,
    MessagingConsumeError,
    # 存储异常
    StorageError,
    StorageConnectionError,
    StorageNotFoundError,
    StoragePermissionError,
    # 配置异常
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigParseError,
    # 网络异常
    NetworkError,
    NetworkConnectionError,
    NetworkTimeoutError,
    # 计算资源异常
    ComputeError,
    ComputeResourceError,
    ComputeQuotaError,
    # 内存异常
    MemoryError,
    MemoryAllocationError,
    MemoryOOMError,
    # 监控异常
    MonitoringError,
    MetricsCollectionError,
    # 日志异常
    LoggingError,
    LogWriteError,
    # 依赖注入异常
    DIError,
    DINavigationError,
    DIRuntimeError,
    # MCP 异常
    MCPError,
    MCPConnectionError,
    MCPToolNotFoundError,
)

__all__ = [
    "__version__",
    # 基础异常
    "InfraError",
    # 数据库异常
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseTimeoutError",
    "DatabaseQueryError",
    "DatabasePoolError",
    # LLM 异常
    "LLMError",
    "LLMConnectionError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMAuthError",
    "LLMModelNotFoundError",
    # 向量存储异常
    "VectorStoreError",
    "VectorStoreConnectionError",
    "VectorStoreTimeoutError",
    "VectorStoreIndexError",
    "VectorStoreDimensionError",
    # 缓存异常
    "CacheError",
    "CacheConnectionError",
    "CacheTimeoutError",
    "CacheKeyError",
    # 消息队列异常
    "MessagingError",
    "MessagingConnectionError",
    "MessagingPublishError",
    "MessagingConsumeError",
    # 存储异常
    "StorageError",
    "StorageConnectionError",
    "StorageNotFoundError",
    "StoragePermissionError",
    # 配置异常
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigValidationError",
    "ConfigParseError",
    # 网络异常
    "NetworkError",
    "NetworkConnectionError",
    "NetworkTimeoutError",
    # 计算资源异常
    "ComputeError",
    "ComputeResourceError",
    "ComputeQuotaError",
    # 内存异常
    "MemoryError",
    "MemoryAllocationError",
    "MemoryOOMError",
    # 监控异常
    "MonitoringError",
    "MetricsCollectionError",
    # 日志异常
    "LoggingError",
    "LogWriteError",
    # 依赖注入异常
    "DIError",
    "DINavigationError",
    "DIRuntimeError",
    # MCP 异常
    "MCPError",
    "MCPConnectionError",
    "MCPToolNotFoundError",
]
