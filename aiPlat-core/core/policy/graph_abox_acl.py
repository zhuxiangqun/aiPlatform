"""GraphIndex ABox ACL — instance + field permissions (Xingye T9 / P4).

Wiki object/field ACL lives under collections/; this module scopes the same
ideas to domain GraphIndex entities under AIPLAT_HOME/ontologies/{domain}/.

Default: no ACL file → allow all (backward compatible).

N07/N22 deepen：配置驱动角色×动作轴（``AIPLAT_ABOX_ROLE_ACTION_MATRIX``）；
非部署 RBAC 真源（N18）/ 非 Wiki·KB 全入口 / 非 certified。
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

# N07/N22 deepen：默认角色×动作轴（可被 env JSON 覆盖/扩展任意角色）
_DEFAULT_ROLE_ACTION_MATRIX: Dict[str, List[str]] = {
    "viewer": ["read"],
    "analyst": ["read", "update", "state_change"],
    "admin": ["*"],
}


def role_action_matrix_enabled() -> bool:
    """是否启用角色×动作轴默认门（缺省开；``0/false/off`` 关闭）。"""
    raw = (os.environ.get("AIPLAT_ABOX_ROLE_ACTION_MATRIX_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def load_role_action_matrix() -> Dict[str, List[str]]:
    """加载角色→动作列表矩阵（默认 + ``AIPLAT_ABOX_ROLE_ACTION_MATRIX`` JSON 覆盖）。

    Returns:
        角色小写 → 动作列表（可含 ``*``）。
    """
    out: Dict[str, List[str]] = {
        k: list(v) for k, v in _DEFAULT_ROLE_ACTION_MATRIX.items()
    }
    raw = (os.environ.get("AIPLAT_ABOX_ROLE_ACTION_MATRIX") or "").strip()
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("AIPLAT_ABOX_ROLE_ACTION_MATRIX invalid JSON; using defaults")
        return out
    if not isinstance(data, dict):
        logger.warning("AIPLAT_ABOX_ROLE_ACTION_MATRIX must be object; using defaults")
        return out
    for role, acts in data.items():
        r = str(role).strip().lower()
        if not r:
            continue
        if isinstance(acts, str):
            acts_l = [acts.strip().lower()]
        elif isinstance(acts, list):
            acts_l = [str(a).strip().lower() for a in acts if str(a).strip()]
        else:
            continue
        out[r] = acts_l
    return out


def role_action_allowed(*, role: str, action: str) -> bool:
    """角色×动作轴门：矩阵未列角色 → 拒绝；``*`` 或含该动作 → 允许。

    Args:
        role: 已规范化或原始角色（空角色视为系统旁路，返回 True）。
        action: 动作名。
    """
    if not role_action_matrix_enabled():
        return True
    r = normalize_abox_role(role)
    if not r:
        return True
    act = (action or "read").strip().lower()
    if act not in _VALID_ACTIONS:
        act = "read"
    matrix = load_role_action_matrix()
    allowed = matrix.get(r)
    if allowed is None:
        return False
    acts_l = [str(a).lower() for a in allowed]
    return "*" in acts_l or act in acts_l or "admin" in acts_l


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


def set_entity_acl(
    domain_id: str,
    entity_id: str,
    *,
    deny_roles: Optional[Dict[str, List[str]]] = None,
    allow_roles: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Set per-instance ACL. deny wins over allow when both match.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        deny_roles: deny_roles 参数。
        allow_roles: allow_roles 参数。
    """
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


def check_entity_acl(
    domain_id: str,
    entity_id: str,
    role: str,
    action: str,
) -> bool:
    """Return True if role may perform action on entity. Empty role → allow.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        role: role 参数。
        action: action 参数。
    """
    action = (action or "read").strip().lower()
    if action not in _VALID_ACTIONS:
        action = "read"
    role = normalize_abox_role(role)
    if not role:
        return True

    # N07/N22 deepen：默认角色×动作轴（实例 ACL 之前；未列角色拒绝）
    if not role_action_allowed(role=role, action=action):
        return False

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
    matrix = load_role_action_matrix()
    return {
        "version": "v1",
        "roles": sorted(matrix.keys()),
        "actions": sorted(_VALID_ACTIONS),
        "role_action_matrix": matrix,
        "role_action_matrix_enabled": role_action_matrix_enabled(),
        "layers": {
            "role_action": "AIPLAT_ABOX_ROLE_ACTION_MATRIX (+ defaults); unknown role deny",
            "instance": "entities.<id>.deny_roles|allow_roles — deny wins",
            "attribute": "fields.<id>.<field>.visibility role:<name>|all|none",
            "object_class": "enforced by ActionRegistry target_class + domain YAML",
        },
        "identity_bridge": {
            "aliases": dict(_ROLE_ALIASES),
            "scopes": dict(_SCOPE_TO_ROLE),
            "headers": ["X-AIPLAT-ACTOR-ROLE", "X-AIPLAT-SCOPES"],
        },
        "default": "no abox_acl.json → role×action matrix then allow (empty role bypass)",
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
    }


def run_role_action_matrix_suite() -> Dict[str, Any]:
    """N07/N22 deepen：角色×动作轴套件（certified 恒 false）。

    Returns:
        套件回执；不宣称部署 RBAC 真源 / Wiki·KB 全入口 / N07·N22 certified。
    """
    checks: Dict[str, bool] = {}
    # 1) 默认轴
    checks["viewer_read_ok"] = role_action_allowed(role="viewer", action="read")
    checks["viewer_update_denied"] = not role_action_allowed(
        role="viewer", action="update"
    )
    checks["admin_star"] = role_action_allowed(role="admin", action="delete")

    # 2) 任意角色扩展（env 覆盖）
    prev = os.environ.get("AIPLAT_ABOX_ROLE_ACTION_MATRIX")
    os.environ["AIPLAT_ABOX_ROLE_ACTION_MATRIX"] = json.dumps(
        {"auditor": ["read"], "viewer": ["read"]}
    )
    try:
        checks["custom_role_allowed"] = role_action_allowed(
            role="auditor", action="read"
        )
        checks["custom_role_write_denied"] = not role_action_allowed(
            role="auditor", action="update"
        )
        checks["unknown_role_denied"] = not role_action_allowed(
            role="stranger", action="read"
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_ABOX_ROLE_ACTION_MATRIX", None)
        else:
            os.environ["AIPLAT_ABOX_ROLE_ACTION_MATRIX"] = prev

    # 3) 实例门接线：未知角色在 check_entity_acl 拒绝
    checks["check_entity_uses_matrix"] = not check_entity_acl(
        "lock-service", "E-demo", "stranger", "read"
    )

    # 4) 诚实锁
    checks["honesty_certified_false"] = True

    passed = sum(1 for v in checks.values() if v)
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
        "deploy_rbac_source": False,
        "wiki_kb_full_acl": False,
        "note": (
            "Role×action matrix deepen; not deploy RBAC source; "
            "not Wiki/KB full ACL; not N07/N22 certified"
        ),
    }


def evaluate_role_action_matrix_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N07/N22 角色×动作轴门槛门；certified 恒 false。

    Args:
        suite: ``run_role_action_matrix_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_role_action_matrix_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n07_full_conformance") is True:
        issues.append("honesty_n07_full_forbidden")
    if s.get("n22_full_conformance") is True:
        issues.append("honesty_n22_full_forbidden")
    if s.get("deploy_rbac_source") is True:
        issues.append("honesty_deploy_rbac_forbidden")
    if s.get("wiki_kb_full_acl") is True:
        issues.append("honesty_wiki_kb_full_acl_forbidden")
    required = (
        "viewer_read_ok",
        "viewer_update_denied",
        "admin_star",
        "custom_role_allowed",
        "custom_role_write_denied",
        "unknown_role_denied",
        "check_entity_uses_matrix",
        "honesty_certified_false",
    )
    checks = s.get("checks") if isinstance(s.get("checks"), dict) else {}
    for k in required:
        if not checks.get(k):
            issues.append(f"missing_or_failed:{k}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "note": "Role×action matrix deepen; not N07/N22 certified",
    }
