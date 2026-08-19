"""P0-B2 回归测试：MFA TOTP 模块。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth.mfa import (
    generate_totp_secret,
    totp_uri,
    verify_totp,
    _hotp,
    is_mfa_enabled,
    require_mfa_for_role,
)


def test_generate_secret_valid_base32():
    import base64
    secret = generate_totp_secret()
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    decoded = base64.b32decode(padded)
    assert len(decoded) == 20


def test_verify_correct_code():
    secret = generate_totp_secret()
    code = _hotp(secret, int(time.time()) // 30)
    assert verify_totp(secret, code)


def test_verify_wrong_code_rejected():
    secret = generate_totp_secret()
    assert not verify_totp(secret, "000000")


def test_verify_short_code_rejected():
    secret = generate_totp_secret()
    assert not verify_totp(secret, "12345")


def test_totp_uri_format():
    secret = generate_totp_secret()
    uri = totp_uri(secret, "admin", issuer="aiPlat")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" in uri
    assert "issuer=aiPlat" in uri


def test_is_mfa_enabled():
    assert is_mfa_enabled({"mfa_enabled": True, "mfa_secret": "x"})
    assert not is_mfa_enabled({"mfa_enabled": False, "mfa_secret": "x"})
    assert not is_mfa_enabled({"mfa_secret": "x"})
    assert not is_mfa_enabled({})


def test_admin_requires_mfa():
    assert require_mfa_for_role("admin")
    assert not require_mfa_for_role("developer")
    assert not require_mfa_for_role("viewer")


def test_admin_api_key_creation_requires_mfa(monkeypatch):
    """P0-5 阶段 3: admin 未启用 MFA 时禁止创建 API Key（422 mfa_required）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi import HTTPException
    from api.rest import routes as R

    # 模拟 admin 身份 + 未启用 MFA 的用户
    class FakeIdentity:
        tenant_id = "t1"
        actor_id = "admin_t1"
        actor_role = "admin"
        scopes = []
        auth_type = "api_key"
        request_id = "r1"

    def fake_identity(req):
        return FakeIdentity()

    monkeypatch.setattr(R, "_resolve_identity", fake_identity)

    class FakeStore:
        def get_auth_user(self, uid):
            return {"user_id": uid, "mfa_enabled": False, "mfa_secret": ""}

    monkeypatch.setattr(R, "platform_store", FakeStore())

    class FakeRequest:
        async def json(self):
            return {"expires_days": 30, "permissions": ["kb:read"], "app_id": "api"}

    async def run():
        try:
            await R.tenant_create_api_key(FakeRequest())
            raise AssertionError("expected HTTPException 422")
        except HTTPException as e:
            assert e.status_code == 422, e.status_code
            assert "mfa_required" in str(e.detail), e.detail

    import asyncio
    asyncio.run(run())


def test_admin_api_key_creation_with_mfa_enabled(monkeypatch):
    """P0-5 阶段 3: admin 已启用 MFA 时可正常创建 API Key。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api.rest import routes as R

    class FakeIdentity:
        tenant_id = "t1"
        actor_id = "admin_t1"
        actor_role = "admin"
        scopes = []
        auth_type = "api_key"
        request_id = "r1"

    monkeypatch.setattr(R, "_resolve_identity", lambda req: FakeIdentity())

    class FakeStore:
        def get_auth_user(self, uid):
            return {"user_id": uid, "mfa_enabled": True, "mfa_secret": "SECRET"}

    monkeypatch.setattr(R, "platform_store", FakeStore())

    class FakeRequest:
        async def json(self):
            return {"expires_days": 30, "permissions": ["kb:read"], "app_id": "api"}

    async def run():
        result = await R.tenant_create_api_key(FakeRequest())
        assert "api_key" in result, result

    import asyncio
    asyncio.run(run())
