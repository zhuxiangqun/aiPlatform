from .base import CacheClient, CacheManager
from .schemas import CacheConfig, CacheStats, PoolConfig, StrategyConfig
from .factory import create_cache_client, create_cache_manager

__all__ = [
    "CacheClient",
    "CacheManager",
    "CacheConfig",
    "CacheStats",
    "PoolConfig",
    "StrategyConfig",
    "create_cache_client",
    "create_cache_manager",
]

try:
    from .redis_client import RedisCacheClient
    from .memory_client import MemoryCacheClient
    from .file_client import FileCacheClient

    __all__.extend(["RedisCacheClient", "MemoryCacheClient", "FileCacheClient"])
except ImportError:
    pass
