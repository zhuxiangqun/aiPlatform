"""Eval object-type adapters — build target contracts for Plan (P3).

Dispatch by object_type only (never ``if agent_id ==``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.target_contract import (
    OBJECT_TYPES,
    build_agent_target_contract,
    build_target_contract,
)

# Default case/set templates per object_type (applicability_draft.json keys).
# prompt/workflow/model mirror agent: 1 core + 3 capability + 2 special.
DEFAULT_SET_IDS: Dict[str, tuple] = {
    "agent": (
        "default/normal",
        "default/missing_info",
        "default/tool_failure",
        "default/noise",
        "default/high_risk",
        "default/multi_turn",
    ),
    "skill": ("skill/trigger", "skill/quality"),
    "api": ("api/chat_pull",),
    "generated_app": ("generated_app/pi_smoke", "generated_app/runs_eval"),
    "prompt": (
        "prompt/basic",
        "prompt/missing_vars",
        "prompt/constraint",
        "prompt/noise",
        "prompt/safety",
        "prompt/multi_slot",
    ),
    "workflow": (
        "workflow/basic",
        "workflow/missing_input",
        "workflow/stage_failure",
        "workflow/noise",
        "workflow/safety",
        "workflow/long_chain",
    ),
    "model": (
        "model/basic",
        "model/missing_info",
        "model/format_constraint",
        "model/noise",
        "model/safety",
        "model/consistency",
    ),
    "dataset": ("dataset/basic",),
    "system": (),
}

# Default capabilities so capability/special packs can match without empty contract.
_DEFAULT_CAPS: Dict[str, tuple] = {
    "prompt": ("clarify_or_ask", "format_constraint", "multi_slot_context"),
    "workflow": ("clarify_or_ask", "error_recovery", "long_chain"),
    "model": ("clarify_or_ask", "format_constraint", "consistency"),
}


def default_set_ids_for_type(object_type: str) -> List[str]:
    ot = (object_type or "").strip()
    return list(DEFAULT_SET_IDS.get(ot) or ())


def build_skill_target_contract(
    *,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    profile = dict(eval_profile or {})
    if capabilities is not None:
        caps = list(capabilities)
    else:
        caps = list(profile.get("capabilities") or ["skill_invoke"])
    return build_target_contract(
        object_type="skill",
        object_id=object_id,
        object_version=object_version or str(profile.get("object_version") or ""),
        capabilities=caps,
        tools=list(profile.get("tools") or []),
        permissions=list(profile.get("permissions") or []),
        target_runtime=list(profile.get("target_runtime") or ["core_skill_execute"]),
        eval_purpose=list(profile.get("eval_purpose") or ["behavior", "regression"]),
        boundaries=profile.get("boundaries") if isinstance(profile.get("boundaries"), dict) else {},
        roles=list(profile.get("roles") or []),
        required_env=list(profile.get("required_env") or []),
        source_refs=list(source_refs or profile.get("source_refs") or ["skill_eval"]),
    )


def build_api_target_contract(
    *,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """External HTTP / chat_pull targets use object_type=api."""
    profile = dict(eval_profile or {})
    oid = object_id if str(object_id).startswith("ext:") else f"ext:{object_id}"
    if capabilities is not None:
        caps = list(capabilities)
    else:
        caps = list(profile.get("capabilities") or ["http_chat_pull"])
    return build_target_contract(
        object_type="api",
        object_id=oid,
        object_version=object_version or str(profile.get("object_version") or ""),
        capabilities=caps,
        tools=list(profile.get("tools") or []),
        permissions=list(profile.get("permissions") or ["network"]),
        target_runtime=list(profile.get("target_runtime") or ["external_pull"]),
        eval_purpose=list(profile.get("eval_purpose") or ["behavior", "compat"]),
        boundaries=profile.get("boundaries")
        if isinstance(profile.get("boundaries"), dict)
        else {"no_workspace_execute": True},
        roles=list(profile.get("roles") or []),
        required_env=list(profile.get("required_env") or []),
        source_refs=list(source_refs or profile.get("source_refs") or ["external_exam"]),
    )


def build_generated_app_target_contract(
    *,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    profile = dict(eval_profile or {})
    if capabilities is not None:
        caps = list(capabilities)
    else:
        caps = list(profile.get("capabilities") or ["pi_export"])
    return build_target_contract(
        object_type="generated_app",
        object_id=object_id,
        object_version=object_version or str(profile.get("object_version") or ""),
        capabilities=caps,
        tools=list(profile.get("tools") or []),
        permissions=list(profile.get("permissions") or []),
        target_runtime=list(profile.get("target_runtime") or ["pi"]),
        eval_purpose=list(profile.get("eval_purpose") or ["compat", "regression"]),
        boundaries=profile.get("boundaries")
        if isinstance(profile.get("boundaries"), dict)
        else {"not_workspace_agent": True},
        roles=list(profile.get("roles") or []),
        required_env=list(profile.get("required_env") or []),
        source_refs=list(source_refs or profile.get("source_refs") or ["generated_app_pi"]),
    )


def build_contract_for_object_type(
    *,
    object_type: str,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[str]] = None,
    permissions: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Single entry: object_type → adapter. Raises on unknown type."""
    ot = (object_type or "").strip()
    if ot not in OBJECT_TYPES:
        raise ValueError(f"invalid object_type: {ot or '(empty)'}")
    if ot == "agent":
        return build_agent_target_contract(
            object_id=object_id,
            object_version=object_version,
            capabilities=capabilities,
            tools=tools,
            permissions=permissions,
            roles=roles,
            eval_profile=eval_profile,
            source_refs=source_refs,
        )
    if ot == "skill":
        return build_skill_target_contract(
            object_id=object_id,
            object_version=object_version,
            capabilities=capabilities,
            eval_profile=eval_profile,
            source_refs=source_refs,
        )
    if ot == "api":
        return build_api_target_contract(
            object_id=object_id,
            object_version=object_version,
            capabilities=capabilities,
            eval_profile=eval_profile,
            source_refs=source_refs,
        )
    if ot == "generated_app":
        return build_generated_app_target_contract(
            object_id=object_id,
            object_version=object_version,
            capabilities=capabilities,
            eval_profile=eval_profile,
            source_refs=source_refs,
        )
    # Generic fallback for prompt/model/dataset/workflow/system
    profile = dict(eval_profile or {})
    tr_default = {
        "prompt": ["fixture", "prompt_execute"],
        "model": ["fixture", "model_generate"],
        "dataset": ["fixture"],
        "workflow": ["workspace_execute", "fixture"],
        "system": ["workspace_execute"],
    }.get(ot, ["fixture"])
    caps = list(capabilities or profile.get("capabilities") or [])
    if not caps:
        caps = list(_DEFAULT_CAPS.get(ot) or [])
    purpose_default = (
        ["behavior", "regression", "safety"]
        if ot in ("prompt", "workflow", "model")
        else ["behavior"]
    )
    return build_target_contract(
        object_type=ot,
        object_id=object_id,
        object_version=object_version or str(profile.get("object_version") or ""),
        capabilities=caps,
        tools=list(tools or profile.get("tools") or []),
        permissions=list(permissions or profile.get("permissions") or []),
        target_runtime=list(profile.get("target_runtime") or tr_default),
        eval_purpose=list(profile.get("eval_purpose") or purpose_default),
        boundaries=profile.get("boundaries") if isinstance(profile.get("boundaries"), dict) else {},
        roles=list(roles or profile.get("roles") or []),
        required_env=list(profile.get("required_env") or []),
        source_refs=list(source_refs or profile.get("source_refs") or [f"{ot}_eval"]),
    )


def advisory_runtime_tier(*, object_type: str, live: bool, target_runtime: Sequence[str]) -> str:
    """Plan-time advisory actual tier (re-annotated at execution)."""
    ot = (object_type or "").strip()
    if not live:
        return "fixture"
    primary = (list(target_runtime) or [""])[0]
    if ot == "agent":
        return "workspace_execute"
    if ot == "skill":
        return "core_skill_execute"
    if ot == "api":
        return "external_pull"
    if ot == "generated_app":
        return "pi" if primary == "pi" else "fixture"
    return primary or "fixture"
