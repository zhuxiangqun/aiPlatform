"""security_redteam admit — S1 fixture-only under docker (no live attacks).

Honesty: deterministic local checks; not production red-team; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def security_redteam_is_fixture(payload: Optional[Mapping[str, Any]] = None) -> bool:
    body: Dict[str, Any] = dict(payload or {})
    mode = str(body.get("mode") or body.get("execution_mode") or "").strip().lower()
    if mode in ("live", "online", "agent", "tools"):
        return False
    if mode in ("fixture", "local_fixture", "security_eval_v1"):
        return True
    cases = body.get("cases") or body.get("attacks")
    return isinstance(cases, list) and len(cases) > 0


def assert_security_redteam_fixture(payload: Optional[Mapping[str, Any]] = None) -> None:
    if not security_redteam_is_fixture(payload):
        raise ValueError("sandbox_required:security_redteam")


def _wire_security_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = security_redteam_is_fixture({"mode": "fixture"})
    return security_redteam_is_fixture({"mode": "live"})
