"""
Config Module - 配置管理

提供多源配置加载、环境变量覆盖、动态配置更新等能力

文档位置：docs/config/index.md

文件结构：
├── __init__.py              # 模块导出
├── base.py                  # ConfigLoader, ConfigSource 接口定义
├── loader.py                # ConfigLoaderImpl 实现
├── config.py                # Config 对象
├── factory.py               # create_config_loader()
├── schemas.py               # 数据模型
├── sources/
│   ├── __init__.py
│   ├── base.py             # ConfigSource 基类实现
│   ├── file_source.py     # FileSource 实现
│   └── env_source.py      # EnvSource 实现
└── validators.py           # 配置校验（预留）

配置源优先级：
- FileSource: 0 (默认) / 75 (环境)
- EnvSource: 100 (最高)
"""

from .base import ConfigLoader, ConfigSource
from .loader import ConfigLoaderImpl
from .config import Config
from .factory import create_config_loader, load_config
from .schemas import (
    DatabaseConfig,
    LLMConfig,
    VectorConfig,
    CacheConfig,
    ConfigLoaderConfig,
    AppConfig,
)

__all__ = [
    "ConfigLoader",
    "ConfigSource",
    "ConfigLoaderImpl",
    "Config",
    "create_config_loader",
    "load_config",
    "DatabaseConfig",
    "LLMConfig",
    "VectorConfig",
    "CacheConfig",
    "ConfigLoaderConfig",
    "AppConfig",
]
