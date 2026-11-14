"""
Management request context (PR-01).

Purpose: forward X-AIPLAT-* identity headers from management to core/platform/app
without having to thread Request objects through every router method.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Dict, Optional


_forward_headers: ContextVar[Optional[Dict[str, str]]] = ContextVar("forward_headers", default=None)


def set_forward_headers(headers: Optional[Dict[str, str]]):
    """set_forward_headers。

    Args:
        headers: headers 参数。
    """
    return _forward_headers.set(headers)


def reset_forward_headers(token) -> None:
    """reset_forward_headers。

    Args:
        token: token 参数。
    """
    _forward_headers.reset(token)


def get_forward_headers() -> Dict[str, str]:
    """获取 forward_headers。
    """
    h = _forward_headers.get()
    return dict(h) if isinstance(h, dict) else {}

