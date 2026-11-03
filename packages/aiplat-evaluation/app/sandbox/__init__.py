"""B3-L sandbox policy (local_stub / docker / microVM prep).

Honesty: local engineering only; microVM prep ≠ live tools;
process_split_authorized=false.
"""
from __future__ import annotations

from app.sandbox.microvm import microvm_ready, microvm_status
from app.sandbox.policy import (
    B3_DOCKER_RUNNERS,
    B3_LOCAL_STUB_RUNNERS,
    sandbox_admits,
    sandbox_backend,
    sandbox_health,
)
from app.sandbox.security_policy import (
    s1_live_enabled,
    security_redteam_admits,
    security_redteam_is_fixture,
    security_redteam_is_live_llm,
)
from app.sandbox.skill_policy import skill_suite_is_fixture

__all__ = [
    "B3_DOCKER_RUNNERS",
    "B3_LOCAL_STUB_RUNNERS",
    "microvm_ready",
    "microvm_status",
    "s1_live_enabled",
    "sandbox_admits",
    "sandbox_backend",
    "sandbox_health",
    "security_redteam_admits",
    "security_redteam_is_fixture",
    "security_redteam_is_live_llm",
    "skill_suite_is_fixture",
]
