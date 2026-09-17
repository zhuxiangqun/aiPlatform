"""GraphIndex ABox ACL — instance + field permissions (Xingye T9 / P4).

Wiki object/field ACL lives under collections/; this module scopes the same
ideas to domain GraphIndex entities under AIPLAT_HOME/ontologies/{domain}/.

Default: no ACL file → allow all (backward compatible).
"""

from __future__ import annotations

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
    """Map login / PolicyGate role strings onto viewer|analyst|admin."""
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

    Priority: explicit body/query role > X-AIPLAT-ACTOR-ROLE header > scopes hint.
    Empty → allow-all (backward compatible with unauthenticated demos).
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
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return os.path.join(home, "ontologies", domain_id, "abox_acl.json")


def load_abox_acl(domain_id: str) -> Dict[str, Any]:
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
    path = _acl_path(domain_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dict(data or {})
    data["updated_at"] = time.time()
    data.setdefault("version", "v1")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_entity_acl(
    domain_id: str,
    entity_id: str,
    *,
    deny_roles: Optional[Dict[str, List[str]]] = None,
    allow_roles: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Set per-instance ACL. deny wins over allow when both match."""
    acl = load_abox_acl(domain_id)
    entry = dict(acl["entities"].get(entity_id) or {})
    if deny_roles is not None:
        entry["deny_roles"] = {str(r): list(acts) for r, acts in deny_roles.items()}
    if allow_roles is not None:
        entry["allow_roles"] = {str(r): list(acts) for r, acts in allow_roles.items()}
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
    """visibility: all | none | role:<name> | scope:<token>."""
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


def check_entity_acl(
    domain_id: str,
    entity_id: str,
    role: str,
    action: str,
) -> bool:
    """Return True if role may perform action on entity. Empty role → allow."""
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
    """Return a copy of payload with field ACL applied."""
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


def seed_demo_data_gov_acl(domain_id: str = "data-gov") -> Dict[str, Any]:
    """Demo ACL: viewer cannot read ghost table; owner_contact admin-only."""
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
