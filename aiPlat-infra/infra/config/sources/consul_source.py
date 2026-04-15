"""
ConsulSource - Consul 配置源实现
"""

from typing import Any, Dict, Optional
import requests
from .base import ConfigSource


class ConsulSource(ConfigSource):
    """Consul 配置源"""

    def __init__(
        self,
        url: str = "http://localhost:8500",
        token: Optional[str] = None,
        path: str = "infra/config",
        priority: int = 80,
    ):
        """
        初始化 Consul 配置源

        Args:
            url: Consul API 地址
            token: Consul ACL token
            path: 配置键路径
            priority: 优先级
        """
        super().__init__(priority)
        self.url = url.rstrip("/")
        self.token = token
        self.path = path.strip("/")
        self._session = requests.Session()
        if token:
            self._session.headers["X-Consul-Token"] = token

    def load(self) -> Dict[str, Any]:
        """
        从 Consul 加载配置

        Returns:
            配置字典
        """
        config = {}
        try:
            response = self._session.get(
                f"{self.url}/v1/kv/{self.path}", params={"recurse": True}
            )
            response.raise_for_status()
            data = response.json()
            for item in data:
                key = item.get("Key", "")
                value = item.get("Value", "")
                if value:
                    import base64

                    try:
                        value = base64.b64decode(value).decode("utf-8")
                    except Exception:
                        pass
                config[key] = value
        except Exception:
            pass
        return config
