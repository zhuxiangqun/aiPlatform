"""Request identity trust decisions for the platform HTTP edge.

Header tenant/actor/role are not credentials. They are accepted only in
explicit dev mode or when the caller presents the internal identity secret.
"""
from __future__ import annotations

import hmac
import os


def _flag(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes", "y")


def header_identity_allowed(presented_secret: str | None) -> bool:
    """True when spoofable identity headers may be trusted.

    ``AIPLAT_PLATFORM_DEV_MODE`` keeps the local management UI path.
    Otherwise ``X-AIPLAT-IDENTITY-SECRET`` must match
    ``AIPLAT_PLATFORM_IDENTITY_SECRET``.
    """
    if _flag("AIPLAT_PLATFORM_DEV_MODE"):
        return True
    expected = os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "").strip()
    got = (presented_secret or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def platform_dev_mode() -> bool:
    return _flag("AIPLAT_PLATFORM_DEV_MODE")
