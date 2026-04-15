from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PoolConfig:
    min_size: int = 5
    max_size: int = 20
    max_overflow: int = 10
    timeout: int = 30
    recycle: int = 3600


@dataclass
class SSLConfig:
    enabled: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    verify_mode: str = "REQUIRED"


@dataclass
class DatabaseConfig:
    type: str = "postgres"
    host: str = "localhost"
    port: int = 5432
    name: str = "ai_platform"
    user: str = "postgres"
    password: str = ""
    pool: Optional[PoolConfig] = None
    ssl: Optional[SSLConfig] = None
    lazy_init: bool = True


@dataclass
class PoolStats:
    size: int = 0
    available: int = 0
    used: int = 0
    overflow: int = 0
    waiting: int = 0
