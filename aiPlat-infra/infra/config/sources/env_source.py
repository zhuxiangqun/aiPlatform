"""
EnvSource - 环境变量配置源实现
"""

import os
from typing import Any, Dict

from .base import ConfigSource


class EnvSource(ConfigSource):
    """环境变量配置源"""

    # 环境变量前缀映射
    PREFIX_MAP = {
        "INFRA_": "",  # 基础设施配置
        "DB_": "database.",  # 数据库配置
        "DATABASE_": "database.",  # 数据库配置
        "LLM_": "llm.",  # LLM配置
        "REDIS_": "cache.",  # Redis配置
        "LOG_": "logging.",  # 日志配置
        "MONITOR_": "monitoring.",  # 监控配置
    }

    def __init__(self, priority: int = 100):
        """
        初始化环境变量配置源

        Args:
            priority: 优先级（默认100，最高）
        """
        super().__init__(priority)

    def load(self) -> Dict[str, Any]:
        """
        加载环境变量配置

        Returns:
            配置字典
        """
        config = {}

        for key, value in os.environ.items():
            config_key = self._convert_env_key(key)
            if config_key:
                config[config_key] = self._parse_value(value)

        return config

    def _convert_env_key(self, env_key: str) -> str:
        """
        将环境变量名转换为配置键

        例如：
        - INFRA_LLM_MODEL -> llm.model
        - DB_HOST -> database.host
        - REDIS_PORT -> cache.port

        Args:
            env_key: 环境变量名

        Returns:
            配置键
        """
        for prefix, config_prefix in self.PREFIX_MAP.items():
            if env_key.startswith(prefix):
                # 移除前缀，转换为小写，将下划线转换为点
                key_part = env_key[len(prefix) :].lower()
                config_key = key_part.replace("_", ".")
                return f"{config_prefix}{config_key}" if config_prefix else config_key

        # 未匹配的前缀，默认转换为小写点号分隔
        return env_key.lower().replace("_", ".")

    def _parse_value(self, value: str) -> Any:
        """
        解析环境变量值

        Args:
            value: 环境变量值

        Returns:
            解析后的值
        """
        # 布尔值
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # 整数
        if value.isdigit():
            return int(value)

        # 浮点数
        if value.replace(".", "", 1).isdigit():
            return float(value)

        # 字符串（保留）
        return value

    def watch(self, callback, interval: float = 1.0):
        """
        监听环境变量变更

        注意：环境变量变更需要进程重启才能生效，
        此处通过轮询检测环境变量变化。

        Args:
            callback: 配置变更回调函数
            interval: 检查间隔（秒）

        Returns:
            ConfigWatcher 实例
        """
        return super().watch(callback, interval)

    def _get_env_hash(self) -> int:
        """获取环境变量哈希值，用于变化检测"""
        import hashlib

        env_str = "&".join(f"{k}={v}" for k, v in sorted(os.environ.items()))
        return hashlib.md5(env_str.encode()).hexdigest()
