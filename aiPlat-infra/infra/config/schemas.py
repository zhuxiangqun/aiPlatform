"""
Config Schemas - 配置数据模型定义
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PoolConfig:
    """数据库连接池配置"""

    min_size: int = 5
    max_size: int = 20
    max_overflow: int = 10
    timeout: int = 30
    recycle: int = 3600


@dataclass
class SSLConfig:
    """SSL配置"""

    enabled: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    verify_mode: str = "REQUIRED"


@dataclass
class DatabaseConfig:
    """数据库配置"""

    type: str = "postgres"
    host: str = "localhost"
    port: int = 5432
    name: str = "ai_platform"
    user: str = "postgres"
    password: str = ""
    pool: PoolConfig = field(default_factory=PoolConfig)
    ssl: Optional[SSLConfig] = None
    lazy_init: bool = True


@dataclass
class LLMConfig:
    """LLM配置"""

    provider: str = "openai"
    model: str = "gpt-4"
    api_key_env: str = "OPENAI_API_KEY"
    timeout: int = 30
    max_retries: int = 3
    rate_limit: Optional[Dict[str, Any]] = None
    fallback: Optional[Dict[str, Any]] = None
    default_params: Optional[Dict[str, Any]] = None


@dataclass
class VectorConfig:
    """向量存储配置"""

    type: str = "milvus"
    host: str = "localhost"
    port: int = 19530
    dimension: int = 1536
    collection: str = "default"
    index_type: str = "HNSW"
    index_params: Optional[Dict[str, Any]] = None
    lazy_init: bool = True


@dataclass
class CacheConfig:
    """缓存配置"""

    type: str = "redis"
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    default_ttl: int = 3600
    max_entries: int = 10000
    key_prefix: str = "ai-platform:"
    lazy_init: bool = True


@dataclass
class LoggingConfig:
    """日志配置"""

    level: str = "INFO"
    format: str = "json"
    output: List[str] = field(default_factory=lambda: ["console"])
    file_path: Optional[str] = None
    max_size: str = "100MB"
    backup_count: int = 10


@dataclass
class MonitoringConfig:
    """监控配置"""

    enabled: bool = True
    port: int = 9090
    prefix: str = "ai_platform_infra"
    health_check_path: str = "/health"
    health_check_interval: int = 30


@dataclass
class ConfigSourceSetting:
    """配置源设置"""

    enabled: bool = True
    priority: int = 0


@dataclass
class FileSourceSetting(ConfigSourceSetting):
    """文件配置源设置"""

    path: str = "config/infra/default.yaml"


@dataclass
class EnvSourceSetting(ConfigSourceSetting):
    """环境变量配置源设置"""

    priority: int = 100


@dataclass
class ConsulSourceSetting(ConfigSourceSetting):
    """Consul配置源设置"""

    url: str = "http://localhost:8500"
    token: Optional[str] = None
    path: str = "infra/config"
    priority: int = 80
    watch: bool = False


@dataclass
class ConfigLoaderConfig:
    """配置加载器配置"""

    file: Optional[FileSourceSetting] = None
    env: Optional[EnvSourceSetting] = None
    consul: Optional[ConsulSourceSetting] = None
    watch_enabled: bool = False
    reload_interval: int = 60
    validate: bool = True


@dataclass
class AppConfig:
    """应用完整配置"""

    database: Optional[DatabaseConfig] = None
    llm: Optional[LLMConfig] = None
    vector: Optional[VectorConfig] = None
    cache: Optional[CacheConfig] = None
    logging: Optional[LoggingConfig] = None
    monitoring: Optional[MonitoringConfig] = None

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号路径"""
        keys = key.split(".")
        value = self
        for k in keys:
            if hasattr(value, k):
                value = getattr(value, k)
            elif isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def has(self, key: str) -> bool:
        """检查配置项是否存在"""
        return self.get(key) is not None

    def as_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        for key in ["database", "llm", "vector", "cache", "logging", "monitoring"]:
            attr = getattr(self, key, None)
            if attr:
                result[key] = attr.__dict__ if hasattr(attr, "__dict__") else attr
        return result
