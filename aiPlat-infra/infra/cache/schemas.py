from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class PoolConfig:
    max_connections: int = 50
    retry_on_timeout: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class StrategyConfig:
    default_ttl: int = 3600
    max_entries: int = 10000
    eviction_policy: str = "lru"


@dataclass
class CacheConfig:
    type: str = "redis"
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    pool: Optional[PoolConfig] = None
    strategy: Optional[StrategyConfig] = None
    key_prefix: str = ""
    lazy_init: bool = True


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    keys: int = 0
    used_memory: int = 0
    hit_rate: float = 0.0
