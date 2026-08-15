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
