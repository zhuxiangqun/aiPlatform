"""Execution-type coercion + production fail-closed for unknown values.

Living Spec: docs/architecture/execution-decision-matrix.md §2.1 / §2.5
"""

from __future__ import annotations

import logging
import os
from typing import FrozenSet, Optional, Tuple

logger = logging.getLogger(__name__)

# Always accepted (runtime paths). hybrid is first-class even if YAML enum lags.
_CORE_TYPES: FrozenSet[str] = frozenset(
    {"handler", "hybrid", "prompt", "python_class", "tool_wrapper"}
)

ENV_FAIL_CLOSED = "AIPLAT_EXECUTION_TYPE_FAIL_CLOSED"
ENV_FAIL_OPEN = "AIPLAT_EXECUTION_TYPE_FAIL_OPEN"


def execution_type_fail_closed() -> bool:
    """Production → hard-fail unknown types; FAIL_OPEN wins (ops escape)."""
    fo = (os.environ.get(ENV_FAIL_OPEN) or "").strip().lower()
    if fo in ("1", "true", "yes", "y", "on"):
        return False
    fc = (os.environ.get(ENV_FAIL_CLOSED) or "").strip().lower()
    if fc in ("1", "true", "yes", "y", "on"):
        return True
    if fc in ("0", "false", "no", "n", "off"):
        return False
    try:
        from core.harness.infrastructure.os_sandbox import is_production_profile

        return bool(is_production_profile())
    except Exception:
        return False


def _known_and_aliases() -> Tuple[FrozenSet[str], dict]:
    known = set(_CORE_TYPES)
    aliases: dict = {"llm": "prompt", "ai": "prompt", "script": "handler", "code": "handler"}
    try:
        from core.harness.registry.registry_loader import load_execution_types

        reg = load_execution_types()
        for c in reg.canonical or []:
            known.add(str(c).strip().lower())
        for k, v in (reg.aliases or {}).items():
            aliases[str(k).strip().lower()] = str(v).strip().lower()
    except Exception:
        logger.debug("execution_types registry load skipped", exc_info=True)
    return frozenset(known), aliases


def coerce_execution_type(
    raw: str,
    *,
    skill_name: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """Normalize ``execution_type`` or reject.

    Returns ``(normalized, None)`` on success, or ``(None, error)`` when hard-fail.
    Empty input → ``("", None)`` so callers may auto-detect.
    Unknown: production / FAIL_CLOSED → error; else WARNING and ``\"prompt\"``.
    """
    et = str(raw or "").strip().lower()
    if not et:
        return "", None

    known, aliases = _known_and_aliases()
    et = aliases.get(et, et)
    if et in known:
        return et, None

    label = skill_name or "?"
    if execution_type_fail_closed():
        return None, (
            f"Skill '{label}': unknown execution_type={raw!r} "
            f"(known={sorted(known)}; production/fail-closed — refuse LLM soft-fallback)"
        )
    logger.warning(
        "Skill '%s': unknown execution_type=%r — treating as prompt (dev soft-fallback). "
        "Set AIPLAT_EXECUTION_TYPE_FAIL_CLOSED=1 or AIPLAT_PROFILE=production to hard-fail.",
        label,
        raw,
    )
    return "prompt", None
