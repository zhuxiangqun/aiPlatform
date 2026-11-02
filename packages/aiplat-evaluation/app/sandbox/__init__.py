"""B3-L sandbox policy (local_stub / docker prototype).

Honesty: local engineering only; not a microVM; process_split_authorized=false.
"""
from __future__ import annotations

from app.sandbox.policy import (
    B3_DOCKER_RUNNERS,
    B3_LOCAL_STUB_RUNNERS,
    sandbox_admits,
    sandbox_backend,
    sandbox_health,
)

__all__ = [
    "B3_DOCKER_RUNNERS",
    "B3_LOCAL_STUB_RUNNERS",
    "sandbox_admits",
    "sandbox_backend",
    "sandbox_health",
]
