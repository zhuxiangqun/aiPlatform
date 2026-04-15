"""
FileSource - 文件配置源实现
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import json

from .base import ConfigSource


class FileSource(ConfigSource):
    """文件配置源（YAML/JSON）"""

    def __init__(self, path: str = "config/infra/default.yaml", priority: int = 0):
        """
        初始化文件配置源

        Args:
            path: 配置文件路径
            priority: 优先级
        """
        super().__init__(priority)
        self._path = path
        self._data: Optional[Dict[str, Any]] = None

    @property
    def path(self) -> str:
        return self._path

    def load(self) -> Dict[str, Any]:
        """
        加载配置文件

        Returns:
            配置字典
        """
        if self._data is not None:
            return self._resolve_env_vars(self._data)

        # 尝试 YAML 格式
        yaml_data = self._load_yaml()
        if yaml_data:
            self._data = yaml_data
            return self._resolve_env_vars(self._data)

        # 尝试 JSON 格式
        json_data = self._load_json()
        if json_data:
            self._data = json_data
            return self._resolve_env_vars(self._data)

        # 文件不存在或解析失败，返回空字典
        return {}

    def _load_yaml(self) -> Optional[Dict[str, Any]]:
        """加载 YAML 文件"""
        try:
            import yaml

            file_path = self._resolve_path(self._path)
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except ImportError:
            # yaml 库未安装，尝试纯 Python 解析
            return self._load_yaml_simple()
        except Exception:
            return None
        return None

    def _load_yaml_simple(self) -> Optional[Dict[str, Any]]:
        """简单 YAML 解析（使用纯 Python）"""
        # 简单的键值对解析，不支持复杂 YAML
        try:
            file_path = self._resolve_path(self._path)
            if not os.path.exists(file_path):
                return None

            result = {}
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        key, value = line.split(":", 1)
                        result[key.strip()] = value.strip()
            return result if result else None
        except Exception:
            return None

    def _load_json(self) -> Optional[Dict[str, Any]]:
        """加载 JSON 文件"""
        try:
            file_path = self._resolve_path(self._path)
            if os.path.exists(file_path) and self._path.endswith(".json"):
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return None
        return None

    def _resolve_path(self, path: str) -> str:
        """解析文件路径"""
        if os.path.isabs(path):
            return path

        # 相对路径：优先当前目录，其次项目根目录
        if os.path.exists(path):
            return path

        # 尝试项目根目录
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        full_path = os.path.join(project_root, path)

        if os.path.exists(full_path):
            return full_path

        return path

    def reload(self) -> Dict[str, Any]:
        """重新加载配置"""
        self._data = None
        return self.load()
