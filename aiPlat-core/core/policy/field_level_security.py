"""
Field-Level Security — per-field, per-entity access control for ontology entities.

Implements cell/field-level data visibility (Palantir CBAC equivalent):
  - Redaction strategies: mask, truncate, replace, remove
  - Per-role, per-scope visibility rules
  - Applies during retrieval and export (not storage — data is stored in full)

Storage: per-collection field_permissions.json

Usage:
    from core.policy.field_level_security import apply_field_level_security
    safe_data = apply_field_level_security(entity_data, actor_role, actor_scopes)

callers:
  - sys_wiki_context (inject filtering)
  - wiki.py export endpoints
  - core_facade
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FieldLevelPermission:
    entity_uri: str
    field_name: str
    visibility: str = "all"               # "all" | "role:admin" | "scope:kb:read:confidential" | "none"
    redaction_strategy: str = "mask"      # "mask" | "truncate" | "replace" | "remove"
    replace_with: str = "[REDACTED]"      # replacement text when strategy=replace
    created_at: str = ""
    created_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uri": self.entity_uri,
            "field_name": self.field_name,
            "visibility": self.visibility,
            "redaction_strategy": self.redaction_strategy,
            "replace_with": self.replace_with if self.redaction_strategy == "replace" else "",
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldLevelPermission":
        return cls(
            entity_uri=data.get("entity_uri", ""),
            field_name=data.get("field_name", ""),
            visibility=data.get("visibility", "all"),
            redaction_strategy=data.get("redaction_strategy", "mask"),
            replace_with=data.get("replace_with", "[REDACTED]"),
            created_at=data.get("created_at", ""),
            created_by=data.get("created_by", ""),
        )


def _permissions_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "field_permissions.json")


def load_field_permissions(collection_id: str = "default") -> List[FieldLevelPermission]:
    path = _permissions_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        return [FieldLevelPermission.from_dict(p) for p in data.get("permissions", [])]
    except Exception:
        logger.error("Failed to load field-level permissions for %s", collection_id, exc_info=True)
        return []


def _save_field_permissions(perms: List[FieldLevelPermission], collection_id: str = "default") -> None:
    path = _permissions_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({
            "version": "v1.0",
            "updated_at": _time.time(),
            "permissions": [p.to_dict() for p in perms],
        }, f, indent=2, ensure_ascii=False)


def set_field_permission(
    entity_uri: str,
    field_name: str,
    visibility: str = "all",
    redaction_strategy: str = "mask",
    *,
    collection_id: str = "default",
) -> FieldLevelPermission:
    u"""Set a field-level permission rule for an entity."""
    valid_strategies = {"mask", "truncate", "replace", "remove"}
    strategy = redaction_strategy if redaction_strategy in valid_strategies else "mask"

    perm = FieldLevelPermission(
        entity_uri=entity_uri,
        field_name=field_name,
        visibility=visibility,
        redaction_strategy=strategy,
        created_at=str(_time.time()),
        created_by="api",
    )

    perms = load_field_permissions(collection_id)
    # Remove existing rule for same entity+field
    perms = [p for p in perms if not (p.entity_uri == entity_uri and p.field_name == field_name)]
    perms.append(perm)
    _save_field_permissions(perms, collection_id)
    return perm


def remove_field_permission(
    entity_uri: str,
    field_name: str = "",
    *,
    collection_id: str = "default",
) -> bool:
    u"""Remove field-level permissions. Pass empty field_name to remove all for entity."""
    perms = load_field_permissions(collection_id)
    before = len(perms)
    if field_name:
        perms = [p for p in perms if not (p.entity_uri == entity_uri and p.field_name == field_name)]
    else:
        perms = [p for p in perms if p.entity_uri != entity_uri]
    _save_field_permissions(perms, collection_id)
    return len(perms) < before


def apply_field_level_security(
    entity_data: Dict[str, Any],
    entity_uri: str = "",
    *,
    actor_role: str = "",
    actor_scopes: Optional[List[str]] = None,
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Apply field-level security redaction to entity data.

    Returns a new dict with sensitive fields redacted according to visibility rules.
    Admin role bypasses all restrictions.
    """
    if actor_role == "admin" or (actor_scopes and "admin" in actor_scopes):
        return dict(entity_data)  # admin sees everything

    actor_scopes = actor_scopes or []
    actor_scopes_set = set(actor_scopes)

    perms = load_field_permissions(collection_id)
    applicable = [
        p for p in perms if p.entity_uri == entity_uri or p.entity_uri == "*"
    ]

    if not applicable:
        return dict(entity_data)

    result = dict(entity_data)
    for perm in applicable:
        if not _can_see_field(perm, actor_role, actor_scopes_set):
            field_name = perm.field_name
            if field_name in result:
                result[field_name] = _redact(
                    result[field_name], perm.redaction_strategy, perm.replace_with
                )
    return result


def apply_field_level_security_batch(
    items: List[Dict[str, Any]],
    *,
    actor_role: str = "",
    actor_scopes: Optional[List[str]] = None,
    collection_id: str = "default",
    title_field: str = "title",
) -> List[Dict[str, Any]]:
    u"""Apply field-level security to a batch of entities, using title_field as entity_uri."""
    from core.harness.knowledge.knowledge_abox_builder import _safe_uri
    AI = "http://aiplat.local/knowledge#"

    results = []
    for item in items:
        title = item.get(title_field, "")
        entity_uri = f"{AI}{_safe_uri(title)}" if title else ""
        results.append(
            apply_field_level_security(
                item, entity_uri,
                actor_role=actor_role, actor_scopes=actor_scopes,
                collection_id=collection_id,
            )
        )
    return results


def _can_see_field(perm: FieldLevelPermission, actor_role: str, actor_scopes: Set[str]) -> bool:
    u"""Check if actor can see this field.

    Returns True if actor is ALLOWED to see (no redaction needed).
    Returns False if redaction should be applied.
    """
    if perm.visibility == "all":
        return True
    if perm.visibility == "none":
        return False
    if perm.visibility.startswith("role:"):
        required_role = perm.visibility[5:]
        return actor_role == required_role
    if perm.visibility.startswith("scope:"):
        required_scope = perm.visibility[6:]
        return required_scope in actor_scopes
    return True  # unknown visibility → default allow


def _redact(value: Any, strategy: str, replace_with: str = "[REDACTED]") -> Any:
    u"""Apply redaction strategy to a value."""
    if strategy == "remove":
        return None
    if strategy == "replace":
        return replace_with
    if strategy == "truncate":
        s = str(value)
        return s[:20] + "..." if len(s) > 20 else s
    if strategy == "mask":
        s = str(value)
        if len(s) <= 4:
            return "*" * len(s)
        return s[:2] + "*" * (len(s) - 4) + s[-2:]
    return value  # unknown strategy → pass through
