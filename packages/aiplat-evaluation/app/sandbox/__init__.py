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
from app.sandbox.security_policy import security_redteam_is_fixture
from app.sandbox.skill_policy import skill_suite_is_fixture

__all__ = [
    "B3_DOCKER_RUNNERS",
    "B3_LOCAL_STUB_RUNNERS",
    "sandbox_admits",
    "sandbox_backend",
    "sandbox_health",
    "security_redteam_is_fixture",
    "skill_suite_is_fixture",
]
