"""tool_backend ↔ runtime_tier map (T0).

Authority: docs/architecture/plans/EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md §4.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

RUNTIME_MAP_SCHEMA = "eval.tool_eval_runtime_map.v1"

TOOL_BACKENDS = frozenset({"none", "mock", "live"})

# Allowed actual runtime_tier values per tool_backend (exam-runtime-tiers aligned).
TOOL_BACKEND_RUNTIME_MAP: Dict[str, Set[str]] = {
    "none": {"fixture", "workspace_execute"},
    "mock": {"fixture", "workspace_execute"},
    "live": {"workspace_execute", "core_skill_execute", "eval_worker", "pi"},
}


def validate_tool_backend_runtime(
    *,
    tool_backend: str,
    runtime_tier: str,
) -> List[str]:
    """Return error codes if backend/tier pair is disallowed.

    Args:
        tool_backend: tool_backend 参数。
        runtime_tier: runtime_tier 参数。
    """
    errors: List[str] = []
    backend = str(tool_backend or "").strip().lower()
    tier = str(runtime_tier or "").strip().lower()
    if backend not in TOOL_BACKENDS:
        errors.append("invalid_tool_backend")
        return errors
    if not tier:
        errors.append("missing_field:runtime_tier")
        return errors
    allowed = TOOL_BACKEND_RUNTIME_MAP.get(backend) or set()
    if tier not in allowed:
        errors.append("tool_backend_runtime_mismatch")
    return errors


def assert_mock_not_claimed_as_live(
    *,
    tool_backend: str,
    runtime_claim_reason: Optional[str] = None,
) -> List[str]:
    """Fail closed if mock backend reason text claims production/live tools.

    Args:
        tool_backend: tool_backend 参数。
        runtime_claim_reason: runtime_claim_reason 参数。
    """
    backend = str(tool_backend or "").strip().lower()
    if backend != "mock":
        return []
    reason = str(runtime_claim_reason or "").lower()
    banned = ("生产工具", "live tool", "microvm", "真实工具已测", "production tool")
    if any(b in reason for b in banned):
        return ["mock_claimed_as_live"]
    return []


def tool_eval_runtime_map_document() -> Dict[str, Any]:
    """Machine-readable map for readiness / docs sync."""
    return {
        "schema": RUNTIME_MAP_SCHEMA,
        "tool_backends": sorted(TOOL_BACKENDS),
        "map": {k: sorted(v) for k, v in sorted(TOOL_BACKEND_RUNTIME_MAP.items())},
        "rules": [
            "tool_backend=mock must not claim live/production tools",
            "A3-A5 T1 default tool_backend=mock",
        ],
    }
