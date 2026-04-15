"""
Config Factory - 配置模块工厂函数
"""

from typing import List, Optional

from .loader import ConfigLoader
from .loader import ConfigLoaderImpl, create_default_sources
from .schemas import (
    ConfigLoaderConfig,
    FileSourceSetting,
    EnvSourceSetting,
    ConsulSourceSetting,
)
from .sources.base import ConfigSource
from .sources.file_source import FileSource
from .sources.env_source import EnvSource


def create_config_loader(config: Optional[ConfigLoaderConfig] = None) -> ConfigLoader:
    """
    创建配置加载器

    参数：
        config: 加载器配置（可选）
            - sources: 配置源列表
            - watch_enabled: 是否启用监听
            - reload_interval: 自动重载间隔（秒）
            - validate: 是否启用校验

    返回：
        ConfigLoader 实例

    示例：
        # 使用默认配置
        loader = create_config_loader()
        config = loader.load()

        # 使用自定义配置
        config = ConfigLoaderConfig(
            file=FileSourceSetting(path="config/infra/production.yaml", priority=75),
            env=EnvSourceSetting(enabled=True, priority=100),
            watch_enabled=False,
            reload_interval=300,
            validate=True
        )
        loader = create_config_loader(config)
    """
    if config is None:
        # 使用默认配置源
        sources = create_default_sources()
        return ConfigLoaderImpl(
            sources=sources, watch_enabled=False, reload_interval=60, validate=True
        )

    # 解析配置源
    sources: List[ConfigSource] = []

    # 文件源
    if config.file and config.file.enabled:
        sources.append(FileSource(path=config.file.path, priority=config.file.priority))

    # 环境变量源
    if config.env and config.env.enabled:
        sources.append(EnvSource(priority=config.env.priority))

    # Consul源
    if config.consul and config.consul.enabled:
        from .sources.consul_source import ConsulSource

        sources.append(
            ConsulSource(
                url=config.consul.url,
                token=config.consul.token,
                path=config.consul.path,
                priority=config.consul.priority
                if hasattr(config.consul, "priority")
                else 80,
            )
        )

    return ConfigLoaderImpl(
        sources=sources,
        watch_enabled=config.watch_enabled,
        reload_interval=config.reload_interval,
        validate=config.validate,
    )


def load_config(path: Optional[str] = None) -> "Config":
    """
    便捷函数：加载配置

    参数：
        path: 可选的配置文件路径

    返回：
        配置对象

    示例：
        config = load_config()
        config = load_config("config/infra/production.yaml")

        # 获取配置
        db_host = config.get("database.host")
        llm_model = config.get("llm.model")
    """
    loader = create_config_loader()
    return loader.load(path)
