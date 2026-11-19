"""GraphIndex ABox ACL — instance + field permissions (Xingye T9 / P4).

Wiki object/field ACL lives under collections/; this module scopes the same
ideas to domain GraphIndex entities under AIPLAT_HOME/ontologies/{domain}/.

Default: no ACL file → allow all (backward compatible).
"""

from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir
from core.harness.knowledge.domain_router import DomainRouter

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"read", "update", "state_change", "delete", "admin"})

# Identity / PolicyGate role → ABox ACL role (T9 productization)
_ROLE_ALIASES: Dict[str, str] = {
    "viewer": "viewer",
    "guest": "viewer",
    "readonly": "viewer",
    "read_only": "viewer",
    "analyst": "analyst",
    "operator": "analyst",
    "developer": "analyst",
    "fde": "analyst",
    "admin": "admin",
    "platform_admin": "admin",
    "system": "admin",
    "owner": "admin",
}

# PolicyGate-style scopes → minimum ABox role
_SCOPE_TO_ROLE: Dict[str, str] = {
    "admin": "admin",
    "kb:admin": "admin",
    "graph:admin": "admin",
    "kb:write": "analyst",
    "graph:write": "analyst",
    "graph:state_change": "analyst",
    "kb:read": "viewer",
    "graph:read": "viewer",
}


def normalize_abox_role(role: str) -> str:
    """Map login / PolicyGate role strings onto viewer|analyst|admin.

    Args:
        role: role 参数。
    """
    r = (role or "").strip().lower()
    if not r:
        return ""
    return _ROLE_ALIASES.get(r, r)


def resolve_abox_actor_role(
    *,
    explicit_role: str = "",
    header_role: str = "",
    scopes: Optional[List[str]] = None,
) -> str:
    """Unify identity role for ABox ACL checks.

    Args:
        explicit_role: explicit_role 参数。
        header_role: header_role 参数。
        scopes: scopes 参数。
    """
    for candidate in (explicit_role, header_role):
        norm = normalize_abox_role(candidate)
        if norm:
            return norm
    scopes = scopes or []
    best = ""
    rank = {"viewer": 1, "analyst": 2, "admin": 3}
    for s in scopes:
        mapped = _SCOPE_TO_ROLE.get(str(s).strip().lower(), "")
        if mapped and rank.get(mapped, 0) > rank.get(best, 0):
            best = mapped
    return best


def _acl_path(domain_id: str) -> str:
    home = get_aiplat_home()
    return os.path.join(home, "ontologies", domain_id, "abox_acl.json")


def load_abox_acl(domain_id: str) -> Dict[str, Any]:
    """load_abox_acl。

    Args:
        domain_id: domain 标识。
    """
    path = _acl_path(domain_id)
    if not os.path.isfile(path):
        return {"version": "v1", "entities": {}, "fields": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        data.setdefault("entities", {})
        data.setdefault("fields", {})
        return data
    except Exception:
        logger.warning("load_abox_acl failed for %s", domain_id, exc_info=True)
        return {"version": "v1", "entities": {}, "fields": {}}


def save_abox_acl(domain_id: str, data: Dict[str, Any]) -> None:
    """save_abox_acl。

    Args:
        domain_id: domain 标识。
        data: data 参数。
    """
    path = _acl_path(domain_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dict(data or {})
    data["updated_at"] = time.time()
    data.setdefault("version", "v1")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _match_condition_value(got: Any, want: Any) -> bool:
    """单键条件值：标量等值；``{$eq}`` / ``{$ne}`` / ``{$in}`` 最小运算符。

    Args:
        got: 实例属性值（可为 None）。
        want: 条件期望；标量或单运算符 dict。
    """
    # 为什么：仅开放 $eq/$ne/$in，禁止表达式语言扩大攻击面与语义漂移
    if isinstance(want, dict) and want:
        if len(want) != 1:
            return False
        op, arg = next(iter(want.items()))
        op_s = str(op)
        if op_s == "$eq":
            return str(got) == str(arg)
        if op_s == "$ne":
            return str(got) != str(arg)
        if op_s == "$in":
            if not isinstance(arg, (list, tuple, set)):
                return False
            got_s = str(got)
            return any(got_s == str(x) for x in arg)
        return False
    return str(got) == str(want)


def match_abox_condition(
    condition: Optional[Dict[str, Any]],
    attrs: Optional[Dict[str, Any]],
) -> bool:
    """H.1 最小 condition：全键匹配；空 condition 恒 True。

    每键支持标量等值，或 ``{$eq|$ne|$in: …}``（非完整表达式语言）。

    Args:
        condition: 可选条件 dict（如 status/tenant_id）。
        attrs: 实例属性；含 metadata/props 回退。无 attrs 且有 condition → False
            （规则不生效，避免无上下文误杀）。
    """
    if not condition:
        return True
    if not isinstance(condition, dict) or not condition:
        return True
    if not attrs or not isinstance(attrs, dict):
        return False
    meta = attrs.get("metadata") if isinstance(attrs.get("metadata"), dict) else {}
    props = attrs.get("props") if isinstance(attrs.get("props"), dict) else {}
    for key, want in condition.items():
        got = attrs.get(key)
        if got is None:
            got = meta.get(key)
        if got is None:
            got = props.get(key)
        if not _match_condition_value(got, want):
            return False
    return True


def set_entity_acl(
    domain_id: str,
    entity_id: str,
    *,
    deny_roles: Optional[Dict[str, List[str]]] = None,
    allow_roles: Optional[Dict[str, List[str]]] = None,
    condition: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Set per-instance ACL. deny wins over allow when both match.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        deny_roles: deny_roles 参数。
        allow_roles: allow_roles 参数。
        condition: 可选 H.1 等值条件；仅匹配时本条 deny/allow 生效。
    """
    acl = load_abox_acl(domain_id)
    entry = dict(acl["entities"].get(entity_id) or {})
    if deny_roles is not None:
        entry["deny_roles"] = {str(r): list(acts) for r, acts in deny_roles.items()}
    if allow_roles is not None:
        entry["allow_roles"] = {str(r): list(acts) for r, acts in allow_roles.items()}
    if condition is not None:
        # 为什么：空 dict 表示清除 condition；None 表示不改动
        if condition:
            entry["condition"] = {str(k): v for k, v in condition.items()}
        else:
            entry.pop("condition", None)
    acl["entities"][entity_id] = entry
    save_abox_acl(domain_id, acl)
    return entry


def set_field_acl(
    domain_id: str,
    entity_id: str,
    field_name: str,
    *,
    visibility: str = "all",
    redaction: str = "mask",
    replace_with: str = "[REDACTED]",
) -> Dict[str, Any]:
    """visibility: all | none | role:<name> | scope:<token>.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        field_name: field_name 参数。
        visibility: visibility 参数。
        redaction: redaction 参数。
        replace_with: replace_with 参数。
    """
    acl = load_abox_acl(domain_id)
    key = f"{entity_id}.{field_name}"
    entry = {
        "visibility": visibility,
        "redaction": redaction,
        "replace_with": replace_with,
    }
    acl["fields"][key] = entry
    save_abox_acl(domain_id, acl)
    return entry


def remove_entity_acl(domain_id: str, entity_id: str) -> bool:
    """Remove per-instance ACL entry. Returns True if an entry was removed.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
    """
    acl = load_abox_acl(domain_id)
    entities = acl.get("entities") or {}
    if entity_id not in entities:
        return False
    del entities[entity_id]
    acl["entities"] = entities
    save_abox_acl(domain_id, acl)
    return True


def remove_field_acl(domain_id: str, entity_id: str, field_name: str) -> bool:
    """Remove ABox field ACL for entity_id.field_name. Returns True if removed.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        field_name: field_name 参数。
    """
    acl = load_abox_acl(domain_id)
    key = f"{entity_id}.{field_name}"
    fields = acl.get("fields") or {}
    if key not in fields:
        return False
    del fields[key]
    acl["fields"] = fields
    save_abox_acl(domain_id, acl)
    return True


def check_entity_acl(
    domain_id: str,
    entity_id: str,
    role: str,
    action: str,
    *,
    attrs: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if role may perform action on entity. Empty role → allow.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        role: role 参数。
        action: action 参数。
        attrs: 可选实例属性；用于 H.1 condition 是否适用本条规则。
    """
    action = (action or "read").strip().lower()
    if action not in _VALID_ACTIONS:
        action = "read"
    role = normalize_abox_role(role)
    if not role:
        return True

    acl = load_abox_acl(domain_id)
    entry = acl.get("entities", {}).get(entity_id) or {}
    if not entry:
        return True
    # 为什么：condition 未匹配 → 本条规则不适用，保持放行（非 deny）
    if not match_abox_condition(entry.get("condition"), attrs):
        return True

    deny = entry.get("deny_roles") or {}
    for r, acts in deny.items():
        if str(r).lower() != role:
            continue
        acts_l = [str(a).lower() for a in (acts or [])]
        if "*" in acts_l or action in acts_l or ("admin" in acts_l):
            return False

    allow = entry.get("allow_roles") or {}
    if allow:
        # If allow list present, role must be explicitly allowed
        matched = False
        for r, acts in allow.items():
            if str(r).lower() != role and str(r) != "*":
                continue
            acts_l = [str(a).lower() for a in (acts or [])]
            if "*" in acts_l or action in acts_l or "admin" in acts_l:
                matched = True
                break
        if not matched:
            return False
    return True


def _field_visible(visibility: str, role: str) -> bool:
    vis = (visibility or "all").strip()
    if vis == "all":
        return True
    if vis == "none":
        return False
    role = normalize_abox_role(role)
    if vis.startswith("role:"):
        wanted = normalize_abox_role(vis[5:].strip())
        return role == wanted
    if vis.startswith("scope:"):
        # scopes not passed here — treat as hidden unless role empty (system)
        return not role
    return True


def redact_entity_fields(
    domain_id: str,
    entity_id: str,
    payload: Dict[str, Any],
    role: str,
) -> Dict[str, Any]:
    """Return a copy of payload with field ACL applied.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        payload: 载荷 dict。
        role: role 参数。
    """
    acl = load_abox_acl(domain_id)
    fields = acl.get("fields") or {}
    if not fields:
        return dict(payload)
    out = dict(payload)
    meta = dict(out.get("metadata") or out.get("props") or {})
    changed = False
    for key, rule in fields.items():
        if not key.startswith(f"{entity_id}."):
            continue
        fname = key[len(entity_id) + 1 :]
        if _field_visible(str(rule.get("visibility") or "all"), role):
            continue
        strategy = str(rule.get("redaction") or "mask")
        if fname in meta:
            if strategy == "remove":
                meta.pop(fname, None)
            else:
                meta[fname] = str(rule.get("replace_with") or "[REDACTED]")
            changed = True
        if fname in out and fname not in ("entity_id", "name", "class", "state"):
            if strategy == "remove":
                out.pop(fname, None)
            else:
                out[fname] = str(rule.get("replace_with") or "[REDACTED]")
            changed = True
    if changed:
        if "metadata" in out or "props" in payload:
            out["metadata"] = meta
        for k, v in meta.items():
            if k in out:
                out[k] = v
    return out


def preview_abox_acl(
    domain_id: str,
    entity_id: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    role: str = "",
    action: str = "read",
) -> Dict[str, Any]:
    """Dry-run ABox ACL for an actor role（管理端预览；不写盘、不宣称 certified）。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        payload: 可选样例载荷；缺省用空 dict（兼作 condition attrs）。
        role: 预览角色。
        action: 预览动作（默认 read）。
    """
    sample = dict(payload or {})
    acl = load_abox_acl(domain_id)
    entry = (acl.get("entities") or {}).get(entity_id) or {}
    cond = entry.get("condition") if isinstance(entry, dict) else None
    cond_matched = match_abox_condition(cond, sample if sample else None)
    allowed = check_entity_acl(domain_id, entity_id, role, action, attrs=sample if sample else None)
    redacted = redact_entity_fields(domain_id, entity_id, sample, role) if allowed else {}
    return {
        "domain_id": domain_id,
        "entity_id": entity_id,
        "role": normalize_abox_role(role) or (role or ""),
        "action": (action or "read").strip().lower() or "read",
        "allowed": bool(allowed),
        "condition": cond or None,
        "condition_matched": bool(cond_matched) if cond else None,
        "redacted": redacted,
        # 为什么：预览仅辅助排障，结构门 ≠ certified
        "certified": False,
    }


def seed_demo_data_gov_acl(domain_id: str = DomainRouter.data_gov_domain()) -> Dict[str, Any]:
    """Demo ACL: viewer cannot read ghost table; owner_contact admin-only.

    Args:
        domain_id: domain 标识。
    """
    set_entity_acl(
        domain_id,
        "TBL-tmp_export",
        deny_roles={"viewer": ["read", "state_change", "update"]},
        allow_roles={"admin": ["*"], "analyst": ["read", "state_change", "update"]},
    )
    set_field_acl(
        domain_id,
        "DA-积分流水",
        "owner_contact",
        visibility="role:admin",
        redaction="replace",
        replace_with="[REDACTED]",
    )
    return load_abox_acl(domain_id)


def crud_matrix_doc() -> Dict[str, Any]:
    """Documented CRUD matrix: object × attribute × instance × action."""
    return {
        "version": "v1",
        "roles": ["viewer", "analyst", "admin"],
        "actions": sorted(_VALID_ACTIONS),
        "layers": {
            "instance": "entities.<id>.deny_roles|allow_roles — deny wins",
            "attribute": "fields.<id>.<field>.visibility role:<name>|all|none",
            "object_class": "enforced by ActionRegistry target_class + domain YAML",
        },
        "identity_bridge": {
            "aliases": dict(_ROLE_ALIASES),
            "scopes": dict(_SCOPE_TO_ROLE),
            "headers": ["X-AIPLAT-ACTOR-ROLE", "X-AIPLAT-SCOPES"],
        },
        "default": "no abox_acl.json → allow all (backward compatible)",
    }
