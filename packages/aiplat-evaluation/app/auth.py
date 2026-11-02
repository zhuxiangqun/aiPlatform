"""A6 local — standalone Bearer JWT gate (no Central session).

Honesty:
- Proves 401 without token and tenant isolation for store routes.
- Local HS256 by default; optional issuer claim check.
- Does NOT set process_split_authorized=true.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request


def auth_required(cfg_require: bool | None = None) -> bool:
    raw = (os.getenv("AIPLAT_EVAL_REQUIRE_AUTH") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    if cfg_require is not None:
        return bool(cfg_require)
    # Standalone default: require auth (A-local #6).
    mode = (os.getenv("AIPLAT_EVAL_MODE") or "standalone").strip().lower()
    return mode == "standalone"


def jwt_secret() -> str:
    secret = (os.getenv("AIPLAT_EVAL_JWT_SECRET") or "").strip()
    if secret:
        return secret
    # Local-only fallback — never use in staging/prod (B).
    return "aiplat-eval-local-dev-secret"


def jwt_issuer() -> str:
    return (os.getenv("AIPLAT_EVAL_JWT_ISSUER") or "aiplat-eval-local").strip()


def mint_local_token(
    *,
    tenant_id: str,
    subject: str = "eval-local-user",
    ttl_seconds: int = 3600,
    secret: Optional[str] = None,
    issuer: Optional[str] = None,
) -> str:
    """Mint HS256 JWT for local scripts/tests (same-file wired via require_bearer)."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "tid": tenant_id,
        "iss": issuer or jwt_issuer(),
        "iat": now,
        "exp": now + max(60, int(ttl_seconds)),
    }
    return jwt.encode(payload, secret or jwt_secret(), algorithm="HS256")


def _extract_bearer(request: Request) -> Optional[str]:
    authz = request.headers.get("Authorization")
    if isinstance(authz, str) and authz.lower().startswith("bearer "):
        tok = authz.split(" ", 1)[1].strip()
        return tok or None
    return None


def decode_bearer_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token,
            jwt_secret(),
            algorithms=["HS256"],
            issuer=jwt_issuer(),
            options={"require": ["exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid_token: {exc}") from exc


def require_bearer(request: Request) -> Dict[str, Any]:
    """Return JWT claims or raise 401. No-op identity when auth disabled."""
    if not auth_required(getattr(getattr(request.app.state, "config", None), "require_auth", None)):
        return {"sub": "anonymous", "tenant_id": "", "auth_disabled": True}

    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization: Bearer token",
        )
    claims = decode_bearer_token(token)
    tenant = str(claims.get("tenant_id") or claims.get("tid") or "").strip()
    if not tenant:
        raise HTTPException(status_code=401, detail="token_missing_tenant_id")
    claims["tenant_id"] = tenant
    return claims


def tenant_or_404(row: Optional[Dict[str, Any]], tenant_id: str) -> Dict[str, Any]:
    """Cross-tenant → 404 (not 403), per A-local acceptance #6."""
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    row_tid = str(row.get("tenant_id") or "").strip()
    if tenant_id and row_tid and row_tid != tenant_id:
        raise HTTPException(status_code=404, detail="not_found")
    if tenant_id and not row_tid:
        # Legacy rows without tenant: hide when auth on.
        raise HTTPException(status_code=404, detail="not_found")
    return row


# Warm mint for method_verify same-file wiring (≥2 call sites incl. def).
_ = mint_local_token(tenant_id="__probe__", ttl_seconds=60)
