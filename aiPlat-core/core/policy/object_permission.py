"""
Object-Level Permission — per-entity, per-action, per-role permission model.

Complements scope-based RBAC with fine-grained access control on individual
ontology entities. Permission inheritance follows ontology relations:
  parentOf(P, C) → C inherits P's READ permission
  cites(A, B)     → B's READ permission extends to A's authorized readers
  hasSource(P, D) → (no inheritance — KB doc permissions are independent)

Storage: per-collection JSON (~/.aiplat/wiki/collections/{id}/permissions.json)

caller: policy_gate.check_kb_access() (Phase 2 three-layer fusion)
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

AI = "http://aiplat.local/knowledge#"

logger = logging.getLogger(__name__)


class ObjectAction(str, Enum):
    READ = "read"
    READ_BODY = "read_body"
    CITE = "cite"
    UPDATE = "update"
    STATE_CHANGE = "state_change"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass
class ObjectPermission:
    entity_uri: str
    role: str
    tenant_id: str
    allowed_actions: Set[ObjectAction]
    granted_by: str = "explicit"
    granted_at: str = ""
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uri": self.entity_uri,
            "role": self.role,
            "tenant_id": self.tenant_id,
            "allowed_actions": [a.value for a in self.allowed_actions],
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObjectPermission":
        return cls(
            entity_uri=data.get("entity_uri", ""),
            role=data.get("role", ""),
            tenant_id=data.get("tenant_id", ""),
            allowed_actions={ObjectAction(a) for a in data.get("allowed_actions", [])},
            granted_by=data.get("granted_by", "explicit"),
            granted_at=data.get("granted_at", ""),
            expires_at=data.get("expires_at"),
        )


def _permissions_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "permissions.json")


def _load(collection_id: str = "default") -> List[ObjectPermission]:
    path = _permissions_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        return [ObjectPermission.from_dict(p) for p in data.get("permissions", [])]
    except Exception:
        logger.warning("Failed to load object permissions for %s", collection_id)
        return []


def _save(permissions: List[ObjectPermission], collection_id: str = "default") -> None:
    path = _permissions_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({
            "version": "v1.0",
            "updated_at": _time.time(),
            "permissions": [p.to_dict() for p in permissions],
        }, f, indent=2, ensure_ascii=False)


def grant_object_permission(
    entity_uri: str,
    role: str,
    actions: List[str],
    tenant_id: str = "default",
    granted_by: str = "api",
    *,
    collection_id: str = "default",
) -> ObjectPermission:
    action_set = {ObjectAction(a) for a in actions if a in {x.value for x in ObjectAction}}
    if not action_set:
        raise ValueError(f"No valid actions in {actions}")

    perms = _load(collection_id)
    existing = next((p for p in perms if p.entity_uri == entity_uri and p.role == role), None)
    if existing:
        existing.allowed_actions.update(action_set)
        existing.granted_by = granted_by
    else:
        perms.append(ObjectPermission(
            entity_uri=entity_uri,
            role=role,
            tenant_id=tenant_id,
            allowed_actions=action_set,
            granted_by=granted_by,
            granted_at=str(_time.time()),
        ))
    _save(perms, collection_id)
    return existing or perms[-1]


def revoke_object_permission(
    entity_uri: str,
    role: str = "",
    action: str = "",
    *,
    collection_id: str = "default",
) -> bool:
    perms = _load(collection_id)
    removed = False

    if not role:
        perms = [p for p in perms if p.entity_uri != entity_uri]
        _save(perms, collection_id)
        return True

    for p in perms:
        if p.entity_uri == entity_uri and p.role == role:
            if action:
                act = ObjectAction(action) if action in {x.value for x in ObjectAction} else None
                if act and act in p.allowed_actions:
                    p.allowed_actions.discard(act)
                    removed = True
            else:
                perms.remove(p)
                removed = True
            break

    _save(perms, collection_id)
    return removed


def check_object_permission(
    entity_uri: str,
    role: str,
    action: str,
    tenant_id: str = "default",
    *,
    collection_id: str = "default",
) -> bool:
    u"""Check if a role has a specific action on a specific entity.

    Includes inheritance:
      - parentOf(P, C): C inherits P's READ
      - cites(A, B): B's READ extends to A's direct readers (not implemented yet)
    """
    act = ObjectAction(action) if action in {x.value for x in ObjectAction} else None
    if act is None:
        return False

    perms = _load(collection_id)

    # Direct permission check for entity
    for p in perms:
        if p.entity_uri == entity_uri and p.role == role:
            if act in p.allowed_actions or ObjectAction.ADMIN in p.allowed_actions:
                return True

    # Inheritance: childOf or parentOf → inherit READ from parent
    if act == ObjectAction.READ:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        parent_uris: List[str] = []
        for t in onto.triples:
            if t.subject == entity_uri and t.predicate == f"{AI}childOf":
                parent_uris.append(t.object)
            if t.object == entity_uri and t.predicate == f"{AI}parentOf":
                parent_uris.append(t.subject)

        for parent_uri in parent_uris:
            for p in perms:
                if p.entity_uri == parent_uri and p.role == role:
                    if ObjectAction.READ in p.allowed_actions or ObjectAction.ADMIN in p.allowed_actions:
                        return True

    return False


def get_effective_permissions(
    entity_uri: str,
    tenant_id: str = "default",
    *,
    collection_id: str = "default",
) -> Dict[str, List[str]]:
    u"""Get all effective permissions for an entity, grouped by role.

    Includes inherited permissions from parent entities.
    """
    perms = _load(collection_id)
    result: Dict[str, Set[str]] = {}

    # Direct permissions
    for p in perms:
        if p.entity_uri == entity_uri and p.tenant_id == tenant_id:
            result.setdefault(p.role, set()).update(
                {a.value for a in p.allowed_actions}
            )

    # Inherited READ from parents
    from core.harness.knowledge.knowledge_ontology import get_ontology
    onto = get_ontology()
    parent_uris: List[str] = []
    for t in onto.triples:
        if t.subject == entity_uri and t.predicate == f"{AI}childOf":
            parent_uris.append(t.object)
        if t.object == entity_uri and t.predicate == f"{AI}parentOf":
            parent_uris.append(t.subject)

    for parent_uri in parent_uris:
        for p in perms:
            if p.entity_uri == parent_uri and p.tenant_id == tenant_id:
                if ObjectAction.READ in p.allowed_actions or ObjectAction.ADMIN in p.allowed_actions:
                    result.setdefault(p.role, set()).add("read")

    return {role: sorted(actions) for role, actions in result.items()}
