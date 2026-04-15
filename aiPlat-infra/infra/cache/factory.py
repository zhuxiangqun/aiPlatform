from typing import Optional
from .base import CacheClient, CacheManager
from .schemas import CacheConfig


def create(cache: Optional[CacheConfig] = None) -> CacheClient:
    """创建缓存客户端（便捷函数）"""
    return create_cache_client(cache)


def create_cache(cache: Optional[CacheConfig] = None) -> CacheClient:
    """创建缓存客户端（便捷函数）"""
    return create_cache_client(cache)


def create_cache_client(config: Optional[CacheConfig] = None) -> CacheClient:
    config = config or CacheConfig()

    if config.type == "redis":
        from .redis_client import RedisCacheClient

        return RedisCacheClient(config)
    elif config.type == "memory":
        from .memory_client import MemoryCacheClient

        return MemoryCacheClient(config)
    elif config.type == "file":
        from .file_client import FileCacheClient

        return FileCacheClient(config)
    else:
        raise ValueError(f"Unknown cache type: {config.type}")


def create_cache_manager(cache_client: CacheClient) -> CacheManager:
    from .manager import DefaultCacheManager

    return DefaultCacheManager(cache_client)
