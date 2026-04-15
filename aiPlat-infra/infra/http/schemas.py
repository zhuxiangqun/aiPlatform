from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TimeoutConfig:
    connect: int = 10
    read: int = 30
    write: int = 30
    pool: int = 5


@dataclass
class RetryConfig:
    enabled: bool = True
    max_attempts: int = 3
    backoff_factor: float = 2.0
    retry_on_status: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )


@dataclass
class PoolConfig:
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: int = 30


@dataclass
class ProxyConfig:
    http: Optional[str] = None
    https: Optional[str] = None


@dataclass
class HTTPCacheConfig:
    enabled: bool = True
    ttl: int = 300


@dataclass
class HTTPConfig:
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    pool: PoolConfig = field(default_factory=PoolConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    headers: Dict[str, str] = field(default_factory=dict)
    cache: HTTPCacheConfig = field(default_factory=HTTPCacheConfig)
