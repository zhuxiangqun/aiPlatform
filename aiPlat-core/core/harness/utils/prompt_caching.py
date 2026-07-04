"""
PromptCaching — inject cache_control breakpoints for provider-side caching.

Aligned with hermes-agent prompt_caching.py (72 lines).
Applies "system_and_3" strategy: cache the system prompt + last 3 non-system
messages in a rolling window.  DeepSeek supports Anthropic-compatible
cache_control, so this works out of the box.

Architecture: core/harness/utils/ — harness utility, no infra dependency.
"""

from __future__ import annotations
import copy
from typing import Any, Dict, List, Optional

# ── Configurable via env ──
import os as _os
_CACHE_ENABLED = _os.getenv("AIPLAT_PROMPT_CACHE_ENABLED", "true") not in ("0", "false", "no")
_CACHE_TTL = int(_os.getenv("AIPLAT_PROMPT_CACHE_TTL", "300") or "300")  # 5 min default
_CACHE_BREAKPOINTS = int(_os.getenv("AIPLAT_PROMPT_CACHE_BREAKPOINTS", "4") or "4")


def apply_cache_control(
    messages: List[Dict[str, Any]],
    cache_ttl: int = _CACHE_TTL,
) -> List[Dict[str, Any]]:
    """Inject cache_control markers into messages for provider-side caching.

    Strategy: "system_and_N" — cache the system prompt plus the last N non-system
    messages.  Uses deep-copy to prevent side effects on the caller's list.

    Args:
        messages: List of {"role": "str", "content": "str"} dicts.
        cache_ttl: Cache TTL in seconds (provider-dependent, default 300s).

    Returns:
        Deep-copied messages with cache_control breakpoints injected.
    """
    if not _CACHE_ENABLED or not messages:
        return messages

    # Deep-copy to prevent side effects on caller's message list
    result = copy.deepcopy(messages)
    cache_marker = {"type": "ephemeral"}  # DeepSeek/Anthropic format

    # Find system messages and mark them
    breakpoints_used = 0
    max_breakpoints = min(_CACHE_BREAKPOINTS, len(result))

    # 1. Cache the last system message (most recent wins)
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "system":
            result[i]["cache_control"] = cache_marker
            breakpoints_used += 1
            break

    # 2. Cache the last N non-system messages (rolling window)
    non_system = [i for i in range(len(result)) if result[i].get("role") != "system"]
    for idx in non_system[- (max_breakpoints - breakpoints_used):]:
        result[idx]["cache_control"] = cache_marker

    return result


def get_cache_status() -> Dict[str, Any]:
    """Return cache configuration status for diagnostic display."""
    return {
        "enabled": _CACHE_ENABLED,
        "ttl_seconds": _CACHE_TTL,
        "breakpoints": _CACHE_BREAKPOINTS,
    }
