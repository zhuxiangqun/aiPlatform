"""
Authentication Service - 认证服务
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
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

        self._api_keys[key_hash] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(days=expires_days),
            "active": True,
            "permissions": permissions or [],
        }
        return api_key

    def verify_api_key(self, api_key: str) -> AuthResult:
        """验证 API Key"""
        if not api_key.startswith("apl_"):
            return AuthResult(success=False, error="Invalid key format")

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self._api_keys.get(key_hash)

        if not key_data:
            return AuthResult(success=False, error="Key not found")

        if not key_data.get("active", False):
            return AuthResult(success=False, error="Key disabled")

        if key_data.get("expires_at") and datetime.now() > key_data["expires_at"]:
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
            return True
        return False

    def get_permissions(self, api_key: str) -> list[str]:
        """获取 API Key 权限列表"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self._api_keys.get(key_hash)
        if key_data and key_data.get("active"):
            return key_data.get("permissions", [])
        return []


authenticator = Authenticator()