"""EvalTarget Contract — eval.target_contract.v1 (object contract P0).

Honesty: building a contract ≠ Plan compilation ≠ accuracy/sufficiency claims.
No agent_id string branching for capabilities.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

SCHEMA = "eval.target_contract.v1"

OBJECT_TYPES = frozenset(
    {
        "agent",
        "prompt",
        "skill",
        "workflow",
        "model",
        "api",
        "generated_app",
        "dataset",
        "system",
    }
)

_VERSION_UNSPECIFIED = "version_unspecified"


def _str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple, set)):
        out: List[str] = []
        for x in v:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    s = str(v).strip()
    return [s] if s else []


def _uniq(items: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        k = str(x).strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def normalize_target_contract(raw: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Normalize/validate a contract dict; raises ValueError on hard errors.

    Args:
        raw: raw 参数。
    """
    src = dict(raw or {})
    schema = str(src.get("schema") or SCHEMA).strip() or SCHEMA
    if schema != SCHEMA:
        raise ValueError(f"unsupported target contract schema: {schema}")

    object_type = str(src.get("object_type") or "").strip()
    if object_type not in OBJECT_TYPES:
        raise ValueError(f"invalid object_type: {object_type or '(empty)'}")

    object_id = str(src.get("object_id") or "").strip()
    if not object_id:
        raise ValueError("object_id required")

    version = str(src.get("object_version") or "").strip() or _VERSION_UNSPECIFIED
    boundaries = src.get("boundaries")
    if boundaries is None:
        boundaries = {}
    if not isinstance(boundaries, dict):
        raise ValueError("boundaries must be an object")

    out = {
        "schema": SCHEMA,
        "object_type": object_type,
        "object_id": object_id,
        "object_version": version,
        "capabilities": _uniq(_str_list(src.get("capabilities"))),
        "tools": _uniq(_str_list(src.get("tools"))),
        "permissions": _uniq(_str_list(src.get("permissions"))),
        "target_runtime": _uniq(_str_list(src.get("target_runtime"))),
        "eval_purpose": _uniq(_str_list(src.get("eval_purpose"))),
        "boundaries": dict(boundaries),
        "roles": _uniq(_str_list(src.get("roles"))),
        "required_env": _uniq(_str_list(src.get("required_env"))),
        "source_refs": _uniq(_str_list(src.get("source_refs"))),
    }
    # Optional honesty marker from eval_profile (explicit | derived_hints)
    ps = str(src.get("profile_source") or "").strip()
    if ps:
        out["profile_source"] = ps
    return out


def build_target_contract(
    *,
    object_type: str,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[str]] = None,
    permissions: Optional[Sequence[str]] = None,
    target_runtime: Optional[Sequence[str]] = None,
    eval_purpose: Optional[Sequence[str]] = None,
    boundaries: Optional[Mapping[str, Any]] = None,
    roles: Optional[Sequence[str]] = None,
    required_env: Optional[Sequence[str]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Build a normalized contract from explicit fields (config-driven).

    Args:
        object_type: object_type 参数。
        object_id: object 标识。
        object_version: object_version 参数。
        capabilities: capabilities 参数。
        tools: tools 参数。
        permissions: permissions 参数。
        target_runtime: target_runtime 参数。
        eval_purpose: eval_purpose 参数。
        boundaries: boundaries 参数。
        roles: roles 参数。
        required_env: required_env 参数。
        source_refs: source_refs 参数。
    """
    return normalize_target_contract(
        {
            "schema": SCHEMA,
            "object_type": object_type,
            "object_id": object_id,
            "object_version": object_version,
            "capabilities": list(capabilities or []),
            "tools": list(tools or []),
            "permissions": list(permissions or []),
            "target_runtime": list(target_runtime or []),
            "eval_purpose": list(eval_purpose or []),
            "boundaries": dict(boundaries or {}),
            "roles": list(roles or []),
            "required_env": list(required_env or []),
            "source_refs": list(source_refs or []),
        }
    )


def build_agent_target_contract(
    *,
    object_id: str,
    object_version: str = "",
    capabilities: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[str]] = None,
    permissions: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Agent contract from explicit profile fields — never ``if agent_id ==``.

    Args:
        object_id: object 标识。
        object_version: object_version 参数。
        capabilities: capabilities 参数。
        tools: tools 参数。
        permissions: permissions 参数。
        roles: roles 参数。
        eval_profile: eval_profile 参数。
        source_refs: source_refs 参数。
    """
    profile = dict(eval_profile or {})
    caps = capabilities if capabilities is not None else profile.get("capabilities")
    tls = tools if tools is not None else profile.get("tools")
    perms = permissions if permissions is not None else profile.get("permissions")
    rls = roles if roles is not None else profile.get("roles")
    tr = profile.get("target_runtime") or ["workspace_execute"]
    purpose = profile.get("eval_purpose") or ["behavior", "regression"]
    boundaries = profile.get("boundaries") if isinstance(profile.get("boundaries"), dict) else {}
    ver = object_version or str(profile.get("object_version") or "").strip()
    contract = build_target_contract(
        object_type="agent",
        object_id=object_id,
        object_version=ver,
        capabilities=_str_list(caps),
        tools=_str_list(tls),
        permissions=_str_list(perms),
        target_runtime=_str_list(tr),
        eval_purpose=_str_list(purpose),
        boundaries=boundaries,
        roles=_str_list(rls),
        required_env=_str_list(profile.get("required_env")),
        source_refs=list(source_refs or _str_list(profile.get("source_refs"))),
    )
    ps = str(profile.get("profile_source") or "").strip()
    if ps:
        contract["profile_source"] = ps
    return contract
