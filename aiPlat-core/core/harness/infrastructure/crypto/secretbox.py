"""
SecretBox: minimal symmetric encryption for secrets stored at rest.

MVP requirements:
- Encrypt adapter api_key at rest in ExecutionStore (SQLite)
- Do not expose plaintext secrets via APIs

Key management:
- Uses env var AIPLAT_SECRET_KEY (Fernet key, urlsafe base64 32 bytes)
- If key is missing, encryption is "not configured" and callers may choose to
  store secrets in plaintext (legacy mode) but should surface warnings.
"""

from __future__ import annotations

import os
from typing import Optional


def _get_key() -> Optional[str]:
    k = (os.getenv("AIPLAT_SECRET_KEY") or "").strip()
    return k or None


def is_configured() -> bool:
    return _get_key() is not None


def _fernet():
    from cryptography.fernet import Fernet

    key = _get_key()
    if not key:
        raise ValueError("AIPLAT_SECRET_KEY is not set")
    return Fernet(key.encode("utf-8"))


def encrypt_str(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    if plaintext == "":
        return ""
    f = _fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_str(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    if token == "":
        return ""
    f = _fernet()
    raw = f.decrypt(token.encode("utf-8"))
    return raw.decode("utf-8")

