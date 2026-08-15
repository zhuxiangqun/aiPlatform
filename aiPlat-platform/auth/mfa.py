"""MFA (TOTP) 支持 — RFC 6238 零依赖实现。

P0-B2: admin 全权限无二步验证的安全缺口。
- TOTP 密钥生成/URI 导出（支持 Google Authenticator 等扫码）
- 基于 HMAC-SHA1 的 TOTP 校验（30s 周期，±1 步容差）
- 集成 auth_users.data_json（mfa_secret / mfa_enabled）

用法：
  from aiPlat_platform.auth.mfa import generate_totp_secret, totp_uri, verify_totp
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Optional


def generate_totp_secret() -> str:
    """生成 20 字节随机 TOTP 密钥，Base32 编码（Google Authenticator 兼容）。"""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def totp_uri(secret_b32: str, account: str, issuer: str = "aiPlat") -> str:
    """生成 otpauth:// URI（供扫码导入 Authenticator）。"""
    import urllib.parse
    label = urllib.parse.quote(f"{issuer}:{account}")
    params = urllib.parse.urlencode({"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": 6, "period": 30})
    return f"otpauth://totp/{label}?{params}"


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    """HMAC-SHA1 动态口令（RFC 4226）。"""
    key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1, digits: int = 6) -> bool:
    """校验 TOTP 码（±window 步容差，默认 ±1 步 = 60s 窗口）。"""
    if not code or not code.isdigit() or len(code) != digits:
        return False
    try:
        counter = int(time.time()) // 30
        for i in range(-window, window + 1):
            if hmac.compare_digest(_hotp(secret_b32, counter + i, digits), code):
                return True
    except Exception:
        return False
    return False


def is_mfa_enabled(user: dict) -> bool:
    """检查用户是否已启用 MFA。"""
    return bool(user.get("mfa_enabled")) and bool(user.get("mfa_secret"))


def require_mfa_for_role(role: str) -> bool:
    """admin 角色强制 MFA（CLAUDE.md §11b）。"""
    return role == "admin"
