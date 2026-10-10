"""Subagent return discipline — condense to parent; isolate child context.

Harness article gap: sub-loops must keep independent context and return only a
compact summary to the main loop (budget / prompt-cache safety). Existing
coordinator already summarizes (~800 chars) when isolate_context=True; this
module makes the rules config-driven and fail-closed in production.

Production callers: SubagentCoordinator.execute_single / continue_execution,
MultiAgent.summarize_subagent_result, DelegateManager (optional).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

ENV_FORCE_ISOLATE = "AIPLAT_SUBAGENT_FORCE_ISOLATE"  # auto|on|off
ENV_MAX_RETURN = "AIPLAT_SUBAGENT_MAX_RETURN_CHARS"  # default 800
ENV_PROFILE = "AIPLAT_PROFILE"

DEFAULT_MAX_RETURN_CHARS = 800


def is_production_profile() -> bool:
    return (os.environ.get(ENV_PROFILE) or "").strip().lower() == "production"


def max_return_chars() -> int:
    try:
        return max(200, min(8000, int(os.environ.get(ENV_MAX_RETURN) or DEFAULT_MAX_RETURN_CHARS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETURN_CHARS


def force_isolate_mode() -> str:
    """auto | on | off — auto = production on."""
    raw = (os.environ.get(ENV_FORCE_ISOLATE) or "auto").strip().lower()
    if raw in ("off", "0", "false", "no", "disabled"):
        return "off"
    if raw in ("on", "1", "true", "yes", "force"):
        return "on"
    return "auto"


def resolve_isolate_context(requested: bool = True) -> Tuple[bool, Dict[str, Any]]:
    """Return (isolate_flag, meta). Production/auto coerces False → True."""
    mode = force_isolate_mode()
    want_force = mode == "on" or (mode == "auto" and is_production_profile())
    coerced = False
    isolate = bool(requested)
    if want_force and not isolate:
        isolate = True
        coerced = True
    return isolate, {
        "requested": bool(requested),
        "isolate": isolate,
        "coerced": coerced,
        "mode": mode,
        "production": is_production_profile(),
    }


def filter_protocol_violations(output: str) -> str:
    """Deterministic strip of tool/thought/code blocks (CLAUDE §5.26)."""
    text = output or ""
    text = re.sub(r"```[\s\S]*?```", "[code removed]", text)
    text = re.sub(
        r"(?:^(?:Action|Tool call|"
        + "\u8c03\u7528\u5de5\u5177|sys_tool_call|sys_skill_call)[:\\s]+.*(?:\\n|$))+",
        "[tool calls removed]\n",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    text = re.sub(
        r"^(?:Thought|Let me think|"
        + "\u601d\u8003|\u63a8\u7406|Reasoning)[:\\s]+.*(?:\\n|$)",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    return text.strip()


def safe_truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in ("\n\n", "。", ". ", "\n", "，", ", "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.6:
            return cut[: idx + len(sep)] + f"\n\n... [condensed from {len(text)} chars]"
    return cut + f"\n\n... [condensed from {len(text)} chars]"


def condense_return(
    output: Any,
    *,
    max_chars: Optional[int] = None,
    filter_protocol: bool = True,
) -> str:
    """Hard envelope for anything returned to the parent loop.

    Sync, deterministic last mile — always ≤ max_chars after protocol filter.
    """
    limit = int(max_chars) if max_chars is not None else max_return_chars()
    if output is None:
        return ""
    if isinstance(output, dict):
        parts = []
        if "answer" in output:
            parts.append(str(output.get("answer") or "")[: max(limit - 80, 100)])
        if output.get("sources"):
            parts.append(f"Sources: {len(output['sources'])}")
        if output.get("errors"):
            parts.append(f"Errors: {len(output['errors'])}")
        if output.get("content") and not parts:
            parts.append(str(output.get("content") or ""))
        text = "\n".join(parts) if parts else str(output)
    else:
        text = str(output)
    if filter_protocol:
        text = filter_protocol_violations(text)
    return safe_truncate(text, limit)


def discipline_status() -> Dict[str, Any]:
    """Diagnostics for production_depth / CoreFacade."""
    mode = force_isolate_mode()
    return {
        "force_isolate_mode": mode,
        "force_isolate_active": mode == "on" or (mode == "auto" and is_production_profile()),
        "max_return_chars": max_return_chars(),
        "profile": (os.environ.get(ENV_PROFILE) or "").strip().lower() or "(unset)",
        "env_force": ENV_FORCE_ISOLATE,
        "env_max": ENV_MAX_RETURN,
    }
