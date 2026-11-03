"""skill_suite admit rules — fixture-only under docker (no live tools).

Honesty: not microVM; not real tool/skill execution; accuracy_claim=false at runner.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def skill_suite_is_fixture(payload: Optional[Mapping[str, Any]] = None) -> bool:
    """True only for explicit fixture payloads without tools."""
    body: Dict[str, Any] = dict(payload or {})
    mode = str(body.get("mode") or body.get("execution_mode") or "").strip().lower()
    if mode in ("live", "tools", "agent", "tool"):
        return False
    tools = body.get("tools")
    if isinstance(tools, list) and len(tools) > 0:
        return False
    if isinstance(tools, dict) and len(tools) > 0:
        return False
    if mode in ("fixture", "local_fixture"):
        return True
    # Explicit cases list without tools also counts as fixture.
    cases = body.get("cases")
    return isinstance(cases, list) and len(cases) > 0


def assert_skill_suite_fixture(payload: Optional[Mapping[str, Any]] = None) -> None:
    if not skill_suite_is_fixture(payload):
        raise ValueError("sandbox_required:skill_suite")


def _wire_skill_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = skill_suite_is_fixture({"mode": "fixture"})
    return skill_suite_is_fixture({"tools": ["shell"]})
