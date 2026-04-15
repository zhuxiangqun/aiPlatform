"""
ConfigSource Base - 配置源抽象基类及实现
"""

from abc import ABC
from typing import Any, Callable, Dict, Optional
import threading
import time
from dataclasses import dataclass, field

from ..base import ConfigSource as ConfigSourceABC


@dataclass
class ConfigChange:
    """配置变更事件"""

    source: "ConfigSource"
    old_config: Dict[str, Any]
    new_config: Dict[str, Any]
    changed_keys: set = field(default_factory=set)


class ConfigWatcher:
    """配置监听器"""

    def __init__(
        self,
        source: "ConfigSource",
        callback: Callable[[ConfigChange], None],
        interval: float = 1.0,
    ):
        self.source = source
        self.callback = callback
        self.interval = interval
        self._running = False
        self._thread = None
        self._last_config: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def start(self):
        """启动监听器"""
        if self._running:
            return
        self._running = True
        self._last_config = self.source.load()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监听器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _watch_loop(self):
        """监听循环"""
        while self._running:
            try:
                new_config = self.source.load()
                with self._lock:
                    changed_keys = self._diff_configs(self._last_config, new_config)
                    if changed_keys:
                        change = ConfigChange(
                            source=self.source,
                            old_config=self._last_config,
                            new_config=new_config,
                            changed_keys=changed_keys,
                        )
                        self.callback(change)
                        self._last_config = new_config
            except Exception:
                pass
            time.sleep(self.interval)

    def _diff_configs(self, old: Dict[str, Any], new: Dict[str, Any]) -> set:
        """比较配置差异"""
        changed = set()
        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                changed.add(key)
        return changed


class ConfigSource(ConfigSourceABC):
    """配置源抽象基类"""

    def __init__(self, priority: int = 0):
        """
        初始化配置源

        Args:
            priority: 配置源优先级（0-100），越高优先级越高
        """
        self._priority = priority
        self._watchers: list[ConfigWatcher] = []

    @property
    def priority(self) -> int:
        """配置源优先级"""
        return self._priority

    def load(self) -> Dict[str, Any]:
        """
        加载配置字典

        Returns:
            配置字典
        """
        raise NotImplementedError("Subclasses must implement load()")

    def watch(
        self, callback: Callable[[ConfigChange], None], interval: float = 1.0
    ) -> ConfigWatcher:
        """
        监听配置变更

        Args:
            callback: 配置变更回调函数
            interval: 检查间隔（秒）

        Returns:
            ConfigWatcher 实例，可用于停止监听
        """
        watcher = ConfigWatcher(self, callback, interval)
        watcher.start()
        self._watchers.append(watcher)
        return watcher

    def stop_watchers(self):
        """停止所有监听器"""
        for watcher in self._watchers:
            watcher.stop()
        self._watchers.clear()

    def _parse_env_vars(self, value: str) -> Any:
        """
        解析环境变量引用

        支持格式：
        - ${VAR_NAME} - 获取环境变量
        - ${VAR_NAME:default} - 获取环境变量，默认值

        Args:
            value: 包含环境变量引用的字符串

        Returns:
            解析后的值
        """
        import os
        import re

        pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

        def replace(match):
            var_name = match.group(1)
            default = match.group(2)
            return os.environ.get(
                var_name, default if default is not None else match.group(0)
            )

        result = re.sub(pattern, replace, str(value))

        # 尝试转换类型
        if result.lower() == "true":
            return True
        elif result.lower() == "false":
            return False
        elif result.isdigit():
            return int(result)
        elif result.replace(".", "", 1).isdigit():
            return float(result)

        return result

    def _flatten_dict(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """将嵌套字典展平为点号分隔的字典"""
        result = {}
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_dict(value, new_key))
            else:
                result[new_key] = value
        return result

    def _resolve_env_vars(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """递归解析字典中的环境变量"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._resolve_env_vars(value)
            elif isinstance(value, str):
                result[key] = self._parse_env_vars(value)
            else:
                result[key] = value
        return result
