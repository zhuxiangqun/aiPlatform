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
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"read", "update", "state_change", "delete", "admin"})

# 为什么：H.1 $regex 仅开放短模式 + 有界主语，降低 ReDoS / 任意编译风险（非完整正则引擎产品）
_REGEX_MAX_PATTERN_LEN = 128
_REGEX_MAX_SUBJECT_LEN = 4096

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


def _as_comparable_number(value: Any) -> Optional[float]:
    """将值规范为可比较数值；bool / 非数字 → None。

    Args:
        value: 属性或条件参数。
    """
    # 为什么：bool 是 int 子类，必须排除，避免 True>$gt:0 误匹配
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _match_regex_condition(got: Any, pattern: Any, options: Any = "") -> bool:
    """有界 ``$regex``；``$options`` 仅允许 ``i``（大小写不敏感）。

    Args:
        got: 实例属性值；None → 不匹配。
        pattern: 正则模式（须为非空 str 且长度 ≤ `_REGEX_MAX_PATTERN_LEN`）。
        options: 可选 flags 字符串；空 / 缺省 = 无 flags；含非 ``i`` 字符 → 拒配。
    """
    # 为什么：仅开放 IGNORECASE，拒绝 m/s/x 等扩大匹配面的 flags
    if got is None:
        return False
    if not isinstance(pattern, str) or not pattern or len(pattern) > _REGEX_MAX_PATTERN_LEN:
        return False
    flags = 0
    if options is None or options == "":
        pass
    elif isinstance(options, str):
        for ch in options:
            if ch == "i":
                flags |= re.IGNORECASE
            else:
                return False
    else:
        return False
    subject = str(got)
    if len(subject) > _REGEX_MAX_SUBJECT_LEN:
        subject = subject[:_REGEX_MAX_SUBJECT_LEN]
    try:
        return re.search(pattern, subject, flags) is not None
    except re.error:
        return False


def _match_condition_value(got: Any, want: Any) -> bool:
    """单键条件值：标量等值；``{$eq|$ne|$in|$exists|$gt|$gte|$lt|$lte|$regex}``（可附 ``$options``）。

    Args:
        got: 实例属性值（可为 None；None 视为字段缺失）。
        want: 条件期望；标量或单运算符 dict（``$regex`` 可与 ``$options`` 同级）。
    """
    # 为什么：仅开放等值/集合/存在/数值比较/有界正则(+i)；禁止嵌套布尔扩大攻击面
    if isinstance(want, dict) and want:
        keys = set(want.keys())
        if "$regex" in keys:
            # 为什么：只允许 {$regex} 或 {$regex,$options}；其它键组合一律拒配
            if keys - {"$regex", "$options"}:
                return False
            return _match_regex_condition(got, want.get("$regex"), want.get("$options", ""))
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
        if op_s == "$exists":
            # 为什么：true→字段存在；false→字段缺失；arg 用 bool() 规范化
            present = got is not None
            return present if bool(arg) else (not present)
        if op_s in ("$gt", "$gte", "$lt", "$lte"):
            left = _as_comparable_number(got)
            right = _as_comparable_number(arg)
            if left is None or right is None:
                return False
            if op_s == "$gt":
                return left > right
            if op_s == "$gte":
                return left >= right
            if op_s == "$lt":
                return left < right
            return left <= right
        return False
    return str(got) == str(want)


def match_abox_condition(
    condition: Optional[Dict[str, Any]],
    attrs: Optional[Dict[str, Any]],
) -> bool:
    """H.1 最小 condition：全键匹配；空 condition 恒 True。

    每键支持标量等值，或 ``{$eq|$ne|$in|$exists|$gt|$gte|$lt|$lte|$regex: …}``
    （``$regex`` 可附 ``$options:"i"``；数值比较仅 int/float；非完整表达式语言）。

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


def _normalize_masked_properties(props: Optional[List[Any]]) -> List[str]:
    """规范化 H.1 masked_properties 列表（去空、去重保序）。

    Args:
        props: 原始属性名列表；None → 空列表。
    """
    out: List[str] = []
    seen = set()
    for p in props or []:
        name = str(p).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def list_masked_properties(domain_id: str, entity_id: str) -> List[str]:
    """读取实体上登记的 H.1 masked_properties。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
    """
    acl = load_abox_acl(domain_id)
    entry = (acl.get("entities") or {}).get(entity_id) or {}
    if not isinstance(entry, dict):
        return []
    return _normalize_masked_properties(entry.get("masked_properties"))


def entity_acl_to_h1(domain_id: str, entity_id: str) -> Dict[str, Any]:
    """将存储态投影为附录 H.1 只读形状（非完整策略编辑器 / certified=false）。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
    """
    acl = load_abox_acl(domain_id)
    entry = (acl.get("entities") or {}).get(entity_id) or {}
    if not isinstance(entry, dict):
        entry = {}
    deny = entry.get("deny_roles") or {}
    allow = entry.get("allow_roles") or {}
    # 为什么：deny 优先投影 effect；多角色时 principals 取 deny 键，否则 allow 键
    if deny:
        effect = "deny"
        principals = [f"role:{r}" for r in deny.keys()]
        actions_src = deny
    else:
        effect = "allow"
        principals = [f"role:{r}" for r in allow.keys()]
        actions_src = allow
    acts: List[str] = []
    seen_a = set()
    for lst in actions_src.values():
        for a in lst or []:
            s = str(a).strip()
            if s and s not in seen_a:
                seen_a.add(s)
                acts.append(s)
    return {
        "resource": entity_id,
        "effect": effect,
        "principals": principals,
        "condition": entry.get("condition") or None,
        "masked_properties": list_masked_properties(domain_id, entity_id),
        "actions": acts,
        "certified": False,
    }


def _principal_to_role(principal: Any) -> str:
    """H.1 principal → ABox 角色名（支持 ``role:x`` / 裸名）。

    Args:
        principal: 主体字符串或可转 str 值。
    """
    s = str(principal or "").strip()
    if not s:
        return ""
    if s.lower().startswith("role:"):
        s = s[5:].strip()
    return normalize_abox_role(s) or s


def apply_h1_policy(
    domain_id: str,
    entity_id: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """将附录 H.1 形状写入存储态（薄导入；非完整策略编辑器 / certified=false）。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识（优先；policy.resource 仅校验）。
        policy: H.1 dict（effect/principals/actions/condition/masked_properties）。
    """
    if not isinstance(policy, dict):
        raise ValueError("h1_policy_must_be_object")
    res = str(policy.get("resource") or "").strip()
    # 为什么：resource 若给出且与 path 不一致则拒绝，避免误写错实体
    if res and res != entity_id:
        raise ValueError("h1_resource_mismatch")
    effect = str(policy.get("effect") or "allow").strip().lower()
    if effect not in ("allow", "deny"):
        raise ValueError("h1_effect_invalid")
    principals = policy.get("principals") or []
    if not isinstance(principals, list):
        raise ValueError("h1_principals_must_be_list")
    actions = policy.get("actions") or ["*"]
    if not isinstance(actions, list):
        raise ValueError("h1_actions_must_be_list")
    act_list = [str(a).strip() for a in actions if str(a).strip()] or ["*"]
    role_map: Dict[str, List[str]] = {}
    for p in principals:
        role = _principal_to_role(p)
        if role:
            role_map[role] = list(act_list)
    cond = policy.get("condition")
    if cond is None:
        cond_arg: Optional[Dict[str, Any]] = {}
    elif isinstance(cond, dict):
        cond_arg = cond
    else:
        raise ValueError("h1_condition_must_be_object")
    masks = policy.get("masked_properties")
    if masks is None:
        masks_arg: Optional[List[Any]] = []
    elif isinstance(masks, list):
        masks_arg = masks
    else:
        raise ValueError("h1_masked_properties_must_be_list")
    # 为什么：单 effect 写入时清空对侧 roles，保证 to_h1 往返一致
    if effect == "deny":
        return set_entity_acl(
            domain_id,
            entity_id,
            deny_roles=role_map,
            allow_roles={},
            condition=cond_arg,
            masked_properties=masks_arg,
        )
    return set_entity_acl(
        domain_id,
        entity_id,
        deny_roles={},
        allow_roles=role_map,
        condition=cond_arg,
        masked_properties=masks_arg,
    )


def list_h1_policies(domain_id: str) -> List[Dict[str, Any]]:
    """列出域内全部实例 ACL 的 H.1 只读投影（非完整策略编辑器 / certified=false）。

    Args:
        domain_id: domain 标识。
    """
    acl = load_abox_acl(domain_id)
    entities = acl.get("entities") or {}
    out: List[Dict[str, Any]] = []
    for eid in sorted(entities.keys()):
        out.append(entity_acl_to_h1(domain_id, str(eid)))
    return out


def set_entity_acl(
    domain_id: str,
    entity_id: str,
    *,
    deny_roles: Optional[Dict[str, List[str]]] = None,
    allow_roles: Optional[Dict[str, List[str]]] = None,
    condition: Optional[Dict[str, Any]] = None,
    masked_properties: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Set per-instance ACL. deny wins over allow when both match.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        deny_roles: deny_roles 参数。
        allow_roles: allow_roles 参数。
        condition: 可选 H.1 等值条件；仅匹配时本条 deny/allow 生效。
        masked_properties: 可选 H.1 脱敏字段名列表；同步 fields 为 visibility=none；
            空列表清除；None 表示不改动。
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
    if masked_properties is not None:
        prev = _normalize_masked_properties(entry.get("masked_properties"))
        new = _normalize_masked_properties(masked_properties)
        # 为什么：先写 entry 再落盘字段 ACL，避免半写入
        if new:
            entry["masked_properties"] = new
        else:
            entry.pop("masked_properties", None)
        acl["entities"][entity_id] = entry
        save_abox_acl(domain_id, acl)
        for fname in new:
            set_field_acl(
                domain_id,
                entity_id,
                fname,
                visibility="none",
                redaction="mask",
                replace_with="[REDACTED]",
            )
        for fname in prev:
            if fname not in new:
                remove_field_acl(domain_id, entity_id, fname)
        return dict((load_abox_acl(domain_id).get("entities") or {}).get(entity_id) or entry)
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
    h1 = entity_acl_to_h1(domain_id, entity_id)
    return {
        "domain_id": domain_id,
        "entity_id": entity_id,
        "role": normalize_abox_role(role) or (role or ""),
        "action": (action or "read").strip().lower() or "read",
        "allowed": bool(allowed),
        "condition": cond or None,
        "condition_matched": bool(cond_matched) if cond else None,
        "masked_properties": list(h1.get("masked_properties") or []),
        "h1_policy": h1,
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
