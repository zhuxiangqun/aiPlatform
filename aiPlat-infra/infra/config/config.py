"""
Config - 配置对象实现
"""

import json
from typing import Any, Dict, Optional
import yaml


class Config:
    """
    配置对象 - 提供配置的读取和操作接口

    支持点号路径访问嵌套配置，如 config.get("database.host")
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """
        初始化配置对象

        Args:
            data: 配置字典
        """
        self._data: Dict[str, Any] = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号路径

        Args:
            key: 配置键，支持点号分隔，如 "database.host"
            default: 默认值

        Returns:
            配置值
        """
        if not key:
            return self._data

        keys = key.split(".")
        value = self._data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        设置配置项（运行时）

        Args:
            key: 配置键，支持点号分隔
            value: 配置值
        """
        keys = key.split(".")
        data = self._data

        for i, k in enumerate(keys[:-1]):
            if k not in data:
                data[k] = {}
            data = data[k]

        data[keys[-1]] = value

    def has(self, key: str) -> bool:
        """
        检查配置项是否存在

        Args:
            key: 配置键

        Returns:
            是否存在
        """
        return self.get(key) is not None

    def as_dict(self) -> Dict[str, Any]:
        """
        返回完整配置字典

        Returns:
            配置字典
        """
        return self._data.copy()

    def to_yaml(self) -> str:
        """
        导出为YAML字符串

        Returns:
            YAML 字符串
        """
        return yaml.dump(self._data, default_flow_style=False, allow_unicode=True)

    def to_json(self) -> str:
        """
        导出为JSON字符串

        Returns:
            JSON 字符串
        """
        return json.dumps(self._data, indent=2, ensure_ascii=False)

    def merge(self, other: "Config") -> "Config":
        """
        合并另一个配置（高优先级覆盖低优先级）

        Args:
            other: 另一个配置对象

        Returns:
            新的配置对象
        """
        merged = self._data.copy()
        other_data = other.as_dict()

        for key, value in other_data.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value

        return Config(merged)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def __repr__(self) -> str:
        return f"Config({self._data})"

    def __str__(self) -> str:
        return json.dumps(self._data, indent=2, ensure_ascii=False)
