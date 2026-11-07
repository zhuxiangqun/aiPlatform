"""Resolve / suggest Agent eval_profile for Plan matching.

Explicit ``config.eval_profile`` wins. Otherwise derive capability hints from
declared skills/tools/permissions via substring rules — never ``if agent_id ==``.
Derived profiles keep sufficiency_claim=false (hint ≠ certified profile).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

# Config-style hint table (capability ← declared skill/tool token substrings).
# Extend via eval_profile on the Agent; do not add agent_id branches here.
_CAPABILITY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("clarify_or_ask", ("clarify", "ask", "question", "missing_info", "追问")),
    ("error_recovery", ("recover", "retry", "failure", "tool_fail", "error_handl")),
    ("multi_turn_memory", ("memory", "multi_turn", "multiturn", "recall", "episodic")),
    ("code_gen", ("code_gen", "codegen", "programmer", "write_code")),
    ("retrieval", ("retriev", "rag", "kb_", "search", "wiki")),
)


def _norm_tokens(items: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for x in items or []:
        if x is None:
            continue
        s = str(x).strip().lower()
        if s:
            out.append(s)
    return out


def derive_capability_hints(
    *,
    skills: Optional[Sequence[Any]] = None,
    tools: Optional[Sequence[Any]] = None,
) -> List[str]:
    """Map declared skill/tool names to capability tags via substring hints."""
    blob = " ".join(_norm_tokens(list(skills or []) + list(tools or [])))
    found: List[str] = []
    for cap, needles in _CAPABILITY_HINTS:
        if any(n in blob for n in needles):
            found.append(cap)
    return found


def build_eval_profile_from_declarations(
    *,
    skills: Optional[Sequence[Any]] = None,
    tools: Optional[Sequence[Any]] = None,
    permissions: Optional[Sequence[Any]] = None,
    roles: Optional[Sequence[Any]] = None,
    config: Optional[Mapping[str, Any]] = None,
    object_version: str = "",
) -> Dict[str, Any]:
    """Build a profile dict. Explicit config.eval_profile short-circuits derivation."""
    cfg = dict(config or {})
    explicit = cfg.get("eval_profile")
    if isinstance(explicit, dict) and explicit:
        out = dict(explicit)
        out.setdefault("profile_source", "explicit")
        if object_version and not out.get("object_version"):
            out["object_version"] = object_version
        return out

    skill_list = list(skills or cfg.get("required_skills") or cfg.get("skills") or [])
    tool_list = list(tools or cfg.get("required_tools") or cfg.get("tools") or [])
    perm_list = list(
        permissions or cfg.get("permissions") or cfg.get("required_permissions") or []
    )
    role_list = list(roles or cfg.get("roles") or [])
    caps = derive_capability_hints(skills=skill_list, tools=tool_list)
    # Also accept capabilities already listed loosely on config
    for c in cfg.get("capabilities") or []:
        s = str(c).strip()
        if s and s not in caps:
            caps.append(s)

    return {
        "profile_source": "derived_hints",
        "capabilities": caps,
        "tools": [str(t) for t in tool_list if str(t).strip()],
        "permissions": [str(p) for p in perm_list if str(p).strip()] or ["read_only"],
        "roles": [str(r) for r in role_list if str(r).strip()],
        "target_runtime": ["workspace_execute"],
        "eval_purpose": ["behavior", "regression"],
        "object_version": object_version or "version_unspecified",
        "boundaries": {
            "derived": True,
            "note": "hints from skills/tools substrings; set config.eval_profile to lock",
        },
    }


async def resolve_agent_eval_profile(agent_id: str) -> Dict[str, Any]:
    """Load AgentInfo and return eval_profile (explicit or derived)."""
    aid = (agent_id or "").strip()
    if not aid:
        raise ValueError("agent_id required")
    from core.harness.evaluation.eval_runner import _resolve_exam_agent_info

    info = await _resolve_exam_agent_info(aid)
    cfg = dict(getattr(info, "config", None) or {})
    # Fallback: top-level AGENT.md eval_profile may live on metadata until reload.
    meta = getattr(info, "metadata", None) or {}
    if isinstance(meta, dict) and "eval_profile" not in cfg and isinstance(meta.get("eval_profile"), dict):
        cfg["eval_profile"] = dict(meta["eval_profile"])
    skills = getattr(info, "skills", None) or []
    tools = getattr(info, "tools", None) or []
    ver = str(getattr(info, "version", None) or "")
    profile = build_eval_profile_from_declarations(
        skills=list(skills),
        tools=list(tools),
        config=cfg,
        object_version=ver,
    )
    profile.setdefault("source_refs", ["resolve_agent_eval_profile"])
    return profile
