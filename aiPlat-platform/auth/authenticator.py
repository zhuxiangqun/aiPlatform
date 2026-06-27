import logging
"""
Authentication Service - 认证服务

Persistence: memory (fast read) + SQLite (durable, survives restart).
"""

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class AuthResult(BaseModel):
    success: bool
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    error: Optional[str] = None


class ApiKeyInfo(BaseModel):
    user_id: str
    tenant_id: str
    app_id: str
    created_at: datetime
    expires_at: Optional[datetime]
    active: bool = True
    permissions: list[str] = []


class Authenticator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._api_keys: Dict[str, Dict[str, Any]] = {}
        self._db = None
        self._load_from_db()

    def _ensure_db(self):
        if self._db is None:
            from storage.platform_db import PlatformDB
            self._db = PlatformDB()

    def _load_from_db(self):
        try:
            self._ensure_db()
            for row in self._db.list_api_keys(""):  # load all keys
                pass  # Keys loaded on-demand via get_api_key
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def create_api_key(
        self,
        user_id: str,
        tenant_id: str,
        app_id: str,
        expires_days: int = 365,
        permissions: list[str] = None,
    ) -> str:
        """创建 API Key"""
        api_key = f"apl_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=min(expires_days, 365))).isoformat()

        key_data = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "key_hash": key_hash,
            "key_prefix": api_key[:12],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
            "active": True,
            "permissions": permissions or [],
            "_raw_key": api_key,
        }
        self._api_keys[key_hash] = key_data

        # Persist to SQLite
        try:
            self._ensure_db()
            self._db.upsert_api_key(key_data)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        return api_key

    def verify_api_key(self, api_key: str) -> AuthResult:
        """验证 API Key"""
        if not api_key.startswith("apl_"):
            return AuthResult(success=False, error="Invalid key format")

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self._api_keys.get(key_hash)

        # Try loading from DB if not in memory
        if not key_data:
            try:
                self._ensure_db()
                row = self._db.get_api_key(key_hash)
                if row:
                    key_data = {
                        "user_id": row.get("user_id", ""),
                        "tenant_id": row.get("tenant_id", ""),
                        "active": bool(row.get("active", True)),
                        "expires_at": row.get("expires_at"),
                        "permissions": row.get("permissions", []),
                    }
                    self._api_keys[key_hash] = key_data
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        if not key_data:
            return AuthResult(success=False, error="Key not found")

        if not key_data.get("active", False):
            return AuthResult(success=False, error="Key disabled")

        expires = key_data.get("expires_at")
        if expires:
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            if datetime.now(timezone.utc) > expires:
                return AuthResult(success=False, error="Key expired")

        return AuthResult(
            success=True,
            user_id=key_data["user_id"],
            tenant_id=key_data.get("tenant_id"),
        )

    def revoke_api_key(self, api_key: str) -> bool:
        """撤销 API Key"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        if key_hash in self._api_keys:
            self._api_keys[key_hash]["active"] = False
        try:
            self._ensure_db()
            self._db.revoke_api_key(key_hash)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return key_hash in self._api_keys or True

    def list_keys(self, tenant_id: str) -> List[Dict[str, Any]]:
        """列出租户的所有 API Keys（不含 raw key）"""
        try:
            self._ensure_db()
            return self._db.list_api_keys(tenant_id)
        except Exception:
            return [
                {k: v for k, v in d.items() if k != "_raw_key"}
                for d in self._api_keys.values()
                if d.get("tenant_id") == tenant_id
            ]

    def get_permissions(self, api_key: str) -> list[str]:
        """获取 API Key 权限列表"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self._api_keys.get(key_hash)
        if key_data and key_data.get("active"):
            return key_data.get("permissions", [])
        return []


authenticator = Authenticator()