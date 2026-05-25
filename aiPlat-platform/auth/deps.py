"""
FastAPI dependency functions for platform-wide auth.

Replaces per-module auth patterns with a single shared module.
Usage:
    from auth.deps import require_auth, require_admin

    @router.post("/endpoint")
    async def handler(_auth: str = Depends(require_auth)):
        ...

Wired to builder_auth via re-export for backward compatibility.

Security model:
    - No env vars set: dev mode (all access allowed, returns "dev-anonymous")
    - AIPLAT_API_KEY set: requires key in X-AIPLAT-API-KEY header or Bearer token
    - AIPLAT_ADMIN_KEY set: admin ops require this separate key
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _get_env(key: str) -> Optional[str]:
    val = os.getenv(key)
    return val.strip() if (val and val.strip()) else None


def _auth_enabled() -> bool:
    return bool(_get_env("AIPLAT_API_KEY") or _get_env("AIPLAT_ADMIN_KEY"))


def _verify_key(candidate: str, env_key: str) -> bool:
    if not candidate or not candidate.strip():
        return False
    return _constant_time_compare(candidate.strip(), env_key)


def _extract_key(request: Request) -> Optional[str]:
    key = request.headers.get("X-AIPLAT-API-KEY")
    if key:
        return key
    authz = request.headers.get("Authorization")
    if isinstance(authz, str) and authz.lower().startswith("bearer "):
        return authz.split(" ", 1)[1].strip()
    return None


async def require_auth(request: Request) -> str:
    api_key_env = _get_env("AIPLAT_API_KEY")
    admin_env = _get_env("AIPLAT_ADMIN_KEY")

    if not api_key_env and not admin_env:
        return "dev-anonymous"

    candidate = _extract_key(request)
    if not candidate:
        raise HTTPException(status_code=401, detail="Missing X-AIPLAT-API-KEY or Bearer token")

    if api_key_env and _verify_key(candidate, api_key_env):
        return "authenticated"

    if admin_env and _verify_key(candidate, admin_env):
        return "admin-authenticated"

    raise HTTPException(status_code=403, detail="Invalid API key")


async def require_admin(request: Request) -> str:
    admin_env = _get_env("AIPLAT_ADMIN_KEY")

    if not admin_env and not _get_env("AIPLAT_API_KEY"):
        return "dev-anonymous"

    candidate = _extract_key(request)
    if not candidate:
        raise HTTPException(status_code=401, detail="Missing X-AIPLAT-API-KEY or Bearer token")

    if admin_env and _verify_key(candidate, admin_env):
        return "admin-authenticated"

    raise HTTPException(status_code=403, detail="Admin access required")
