"""Platform edge must not treat spoofed headers or bad JWTs as login."""
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth.request_identity import header_identity_allowed
from governance.quota.quota_manager import Quota, QuotaManager
from governance.rate_limit.limiter import RedisRateLimiter


class _Req:
    def __init__(self, headers):
        self.headers = headers


def _b64(obj) -> str:
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_headers_alone_do_not_grant_identity(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    assert header_identity_allowed(None) is False
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(_Req({
        "X-AIPLAT-TENANT-ID": "victim",
        "X-AIPLAT-ACTOR-ID": "admin",
        "X-AIPLAT-ACTOR-ROLE": "admin",
        "X-AIPLAT-SCOPES": "admin",
    }))
    assert ident.auth_type == "anonymous"
    assert ident.actor_id == "anonymous"
    assert ident.actor_role is None


def test_dev_mode_still_trusts_headers(monkeypatch):
    monkeypatch.setenv("AIPLAT_PLATFORM_DEV_MODE", "1")
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(_Req({
        "X-AIPLAT-TENANT-ID": "local",
        "X-AIPLAT-ACTOR-ID": "admin",
        "X-AIPLAT-ACTOR-ROLE": "admin",
    }))
    assert ident.auth_type == "header"
    assert ident.actor_id == "admin"


def test_identity_secret_trusts_headers(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "s3cret-value")
    assert header_identity_allowed("s3cret-value") is True
    assert header_identity_allowed("wrong-value!") is False
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(_Req({
        "X-AIPLAT-TENANT-ID": "t1",
        "X-AIPLAT-ACTOR-ID": "svc",
        "X-AIPLAT-IDENTITY-SECRET": "s3cret-value",
    }))
    assert ident.auth_type == "header"
    assert ident.tenant_id == "t1"


def test_bad_jwt_is_rejected_not_decoded(monkeypatch):
    monkeypatch.setenv("AIPLAT_PLATFORM_JWT_VERIFY", "true")
    monkeypatch.setenv("AIPLAT_JWT_SECRET", "unit-test-secret")
    from fastapi import HTTPException
    from api.rest.routes import _decode_jwt_claims

    token = f"{_b64({'alg': 'none'})}.{_b64({'sub': 'attacker', 'tid': 'other'})}.sig"
    with pytest.raises(HTTPException) as ei:
        _decode_jwt_claims(token)
    assert ei.value.status_code == 401


def test_anonymous_execute_rejected_outside_dev(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    from fastapi import HTTPException
    from api.rest.routes import Identity, _reject_anonymous_execute

    with pytest.raises(HTTPException) as ei:
        _reject_anonymous_execute(Identity(
            request_id="r",
            tenant_id="default",
            actor_id="anonymous",
            scopes=[],
            auth_type="anonymous",
        ))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_redis_limiter_fails_closed_when_configured(monkeypatch):
    limiter = RedisRateLimiter()
    limiter._redis_url = "redis://127.0.0.1:1"

    async def _down():
        return False

    monkeypatch.setattr(limiter, "_ensure_redis", _down)
    assert await limiter.check("k") is False


def test_unknown_quota_resource_is_denied():
    qm = QuotaManager()
    qm._quotas["t"] = Quota(tenant_id="t")
    assert qm.check("t", "not-a-resource") is False
