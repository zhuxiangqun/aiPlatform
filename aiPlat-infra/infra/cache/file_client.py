"""file_client：模块接口。"""

import json
import os
import shutil
from pathlib import Path
from typing import Optional, List, Any
from .base import CacheClient
from .schemas import CacheConfig


class FileCacheClient(CacheClient):
    """FileCacheClient。"""
    def __init__(self, config: CacheConfig):
        """初始化。

        Args:
            config: config 参数。
        """
        self.config = config
        self._cache_dir = Path(config.key_prefix or os.getenv("AIPLAT_CACHE_PATH", ""))
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.cache"

    def _get_ttl_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.ttl"

    async def get(self, key: str) -> Optional[Any]:
        """get。

        Args:
            key: key 参数。
        """
        path = self._get_path(key)
        ttl_path = self._get_ttl_path(key)

        if not path.exists():
            return None

        if ttl_path.exists():
            import time

            ttl = int(ttl_path.read_text())
            if time.time() > ttl:
                await self.delete(key)
                return None

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return path.read_text(encoding="utf-8")

    async def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        """set。

        Args:
            key: key 参数。
            value: value 参数。
            ttl: ttl 参数。
        """
        path = self._get_path(key)
        ttl_path = self._get_ttl_path(key)

        serialized = json.dumps(value) if not isinstance(value, str) else value
        path.write_text(serialized, encoding="utf-8")

        if ttl > 0:
            import time

            ttl_path.write_text(str(int(time.time() + ttl)), encoding="utf-8")
        elif ttl_path.exists():
            ttl_path.unlink()

        return True

    async def delete(self, key: str) -> bool:
        """delete。

        Args:
            key: key 参数。
        """
        path = self._get_path(key)
        ttl_path = self._get_ttl_path(key)
        deleted = False

        if path.exists():
            path.unlink()
            deleted = True
        if ttl_path.exists():
            ttl_path.unlink()

        return deleted

    async def exists(self, key: str) -> bool:
        """exists。

        Args:
            key: key 参数。
        """
        return self._get_path(key).exists()

    async def clear(self) -> None:
        """clear。
        """
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def keys(self, pattern: str) -> List[str]:
        """keys。

        Args:
            pattern: pattern 参数。
        """
        import fnmatch

        keys = []
        for path in self._cache_dir.glob("*.cache"):
            key = path.stem
            if fnmatch.fnmatch(key, pattern):
                keys.append(key)
        return keys

    async def expire(self, key: str, ttl: int) -> bool:
        """expire。

        Args:
            key: key 参数。
            ttl: ttl 参数。
        """
        if not await self.exists(key):
            return False
        import time

        ttl_path = self._get_ttl_path(key)
        ttl_path.write_text(str(int(time.time() + ttl)), encoding="utf-8")
        return True

    async def ttl(self, key: str) -> int:
        """ttl。

        Args:
            key: key 参数。
        """
        ttl_path = self._get_ttl_path(key)
        if not ttl_path.exists():
            return -1
        import time

        remaining = int(ttl_path.read_text()) - int(time.time())
        return remaining if remaining > 0 else -2
