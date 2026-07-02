"""
Identity Provider — OIDC/OAuth2 身份提供者集成。

支持 Keycloak, Azure AD, Okta 等任何 OIDC 兼容的 IdP。
通过 discovery_url 自动获取配置（jwks_uri, token_endpoint 等）。

Usage:
    provider = OIDCProvider(discovery_url="https://keycloak.example.com/realms/myorg")
    identity = await provider.verify_token(id_token)

环境变量:
    AIPLAT_OIDC_DISCOVERY_URL: OIDC discovery 端点
    AIPLAT_OIDC_CLIENT_ID: 客户端 ID
    AIPLAT_OIDC_CLIENT_SECRET: 客户端密钥
    AIPLAT_OIDC_ENABLED: 是否启用 (true/false)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


class OIDCProvider:
    """OIDC 身份提供者 — 支持标准 OIDC/OAuth2 协议。"""

    def __init__(
        self,
        discovery_url: str = "",
        client_id: str = "",
        client_secret: str = "",
    ):
        self._discovery_url = discovery_url or os.getenv("AIPLAT_OIDC_DISCOVERY_URL", "")
        self._client_id = client_id or os.getenv("AIPLAT_OIDC_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("AIPLAT_OIDC_CLIENT_SECRET", "")
        self._enabled = os.getenv("AIPLAT_OIDC_ENABLED", "false").lower() in ("1", "true", "yes")
        self._config: Dict[str, Any] = {}
        self._jwks: Dict[str, Any] = {}
        self._discovered = False

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._discovery_url)

    async def _ensure_discovery(self):
        """从 discovery_url 获取 OIDC 配置（仅首次）。"""
        if self._discovered or not self._discovery_url:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self._discovery_url)
            resp.raise_for_status()
            self._config = resp.json()

            jwks_url = self._config.get("jwks_uri", "")
            if jwks_url:
                jwks_resp = await client.get(jwks_url)
                self._jwks = jwks_resp.json()
        self._discovered = True

    async def verify_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """验证 id_token 并返回 claims。

        返回 None 表示验证失败。
        """
        if not self.enabled or not id_token:
            return None
        await self._ensure_discovery()

        try:
            from jose import jwt as jose_jwt
            from jose.exceptions import JWTError

            # 获取 issuer 和 audience
            issuer = self._config.get("issuer", "")
            audience = self._client_id

            # 验证签名和 claims
            claims = jose_jwt.decode(
                id_token,
                key=self._jwks,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
                options={"verify_exp": True},
            )
            return claims
        except ImportError:
            # python-jose 未安装 → 回退到不验证的模式（仅适合开发环境）
            return self._decode_unsigned(id_token)
        except JWTError as e:
            logger.warning("JWT verification failed: %s", e)
            return None
        except Exception:
            logger.error("Unexpected error during JWT verification", exc_info=True)
            return None

    def _decode_unsigned(self, id_token: str) -> Optional[Dict[str, Any]]:
        """开发环境回退：不解签名，仅解析 payload（安全警告：仅 dev）。"""
        try:
            parts = id_token.split(".")
            if len(parts) < 2:
                return None
            import base64
            payload = parts[1]
            # 补齐 padding
            payload += "=" * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
            return json.loads(decoded)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Failed to decode unsigned JWT payload: %s", e)
            return None
        except Exception:
            logger.error("Unexpected error decoding unsigned JWT", exc_info=True)
            return None

    def extract_identity(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        """从 OIDC claims 提取 aiPlat Identity 信息。

        映射规则（可被环境变量覆盖）:
            preferred_username → actor_id
            realm / tid          → tenant_id
            realm_access.roles   → scopes
        """
        actor_id = claims.get(
            os.getenv("AIPLAT_OIDC_CLAIM_USERNAME", "preferred_username"),
            claims.get("sub", "anonymous"),
        )
        tenant_id = claims.get(
            os.getenv("AIPLAT_OIDC_CLAIM_TENANT", "tid"),
            claims.get("realm", "default"),
        )
        realm_access = claims.get("realm_access", {})
        roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
        scopes = _map_roles_to_scopes(roles)

        return {
            "tenant_id": str(tenant_id) if tenant_id else "default",
            "actor_id": str(actor_id),
            "scopes": scopes,
            "actor_role": roles[0] if roles else "",
            "auth_type": "oidc",
        }

    async def exchange_code(self, code: str, redirect_uri: str) -> Optional[str]:
        """授权码 → id_token（Authorization Code Flow）。"""
        if not self.enabled:
            return None
        await self._ensure_discovery()

        token_endpoint = self._config.get("token_endpoint", "")
        if not token_endpoint:
            return None

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("id_token") or data.get("access_token")

    def get_authorization_url(self, redirect_uri: str, state: str = "") -> str:
        """生成 IdP 授权页面 URL（用于前端重定向）。"""
        if not self._config:
            return ""
        auth_endpoint = self._config.get("authorization_endpoint", "")
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": os.getenv("AIPLAT_OIDC_SCOPE", "openid profile email"),
            "state": state or "aiplat",
        }
        return f"{auth_endpoint}?{urlencode(params)}"


def _map_roles_to_scopes(roles: List[str]) -> List[str]:
    """将 Keycloak realm roles 映射为 aiPlat scopes。"""
    scope_map = {
        "kb_admin": ["kb:read", "kb:write", "kb:admin"],
        "kb_editor": ["kb:read", "kb:write"],
        "kb_viewer": ["kb:read"],
        "agent_admin": ["agent:execute", "agent:manage"],
        "agent_user": ["agent:execute"],
        "platform_admin": ["*"],
    }
    scopes: List[str] = []
    for role in roles:
        scopes.extend(scope_map.get(role, []))
    return list(set(scopes)) if scopes else ["kb:read"]


# 全局单例
_oidc_provider: Optional[OIDCProvider] = None


def get_oidc_provider() -> OIDCProvider:
    global _oidc_provider
    if _oidc_provider is None:
        _oidc_provider = OIDCProvider()
    return _oidc_provider
