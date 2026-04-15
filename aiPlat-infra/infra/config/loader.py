"""
Config Loader Implementation - 配置加载器实现

具体实现类和辅助函数
"""

from typing import Any, Callable, Dict, List, Optional

from .base import ConfigLoader
from .config import Config


class ConfigLoaderImpl(ConfigLoader):
    """配置加载器实现"""

    def __init__(
        self,
        sources: Optional[List[Any]] = None,
        watch_enabled: bool = False,
        reload_interval: int = 60,
        validate: bool = True,
    ):
        self._sources = sources or []
        self._config: Optional[Config] = None
        self._watch_callbacks: List[Callable[[List[str], Config], None]] = []
        self._watch_enabled = watch_enabled
        self._reload_interval = reload_interval
        self._validate = validate

    def add_source(self, source: Any) -> None:
        """添加配置源"""
        self._sources.append(source)

    def load(self, path: Optional[str] = None) -> Config:
        """加载配置"""
        config_dict: Dict[str, Any] = {}

        for source in sorted(self._sources, key=lambda s: s.priority):
            try:
                source_config = source.load()
                config_dict.update(source_config)
            except Exception as e:
                print(f"Warning: Failed to load from {source}: {e}")

        self._config = Config(config_dict)
        return self._config

    def reload(self) -> Config:
        """重载配置"""
        return self.load()

    def watch(self, callback: Callable[[List[str], Config], None]) -> None:
        """监听配置变更"""
        self._watch_callbacks.append(callback)

    def _notify_watchers(self, changed_keys: List[str]) -> None:
        """通知监听器"""
        if self._config:
            for callback in self._watch_callbacks:
                try:
                    callback(changed_keys, self._config)
                except Exception:
                    pass

    @property
    def sources(self) -> List[Any]:
        """获取配置源列表"""
        return self._sources

    @property
    def config(self) -> Optional[Config]:
        """获取当前配置"""
        return self._config


def create_default_sources() -> List[Any]:
    """创建默认配置源"""
    from .sources.file_source import FileSource
    from .sources.env_source import EnvSource

    sources = []

    # 默认文件源
    try:
        sources.append(FileSource(path="config/infra/default.yaml", priority=0))
    except Exception:
        pass

    # 环境变量源（默认启用）
    try:
        sources.append(EnvSource(priority=100))
    except Exception:
        pass

    return sources
