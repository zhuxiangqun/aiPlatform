u"""
Role View Resolver — 职责维度本体投影 (v2.6).

Implements role-based ontology views:
  - Terminology override: same term, different definition by role
  - Class visibility: which classes a role can see
  - Field filtering: which fields are hidden from a role
  - View inheritance: extends parent view, overrides specific fields

YAML schema:
  views:
    planner:
      extends: base_view      # optional
      label: 计划员
      terminology:            # role-specific term definitions
        readiness:
          definition: "计划已批准 AND 供应商已确认"
      visible_classes: [Order, Supplier, ProductionPlan]
      hidden_fields:
        Order: [actual_cost, profit_margin]
      default_filters:
        Order: { status: [created, confirmed] }
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("role_view")

ViewDefinition = Dict[str, Any]


def load_views(domain_yaml_raw: Dict[str, Any]) -> Dict[str, ViewDefinition]:
    u"""Pre-compile views from raw YAML into role → ViewDefinition mapping (O(1) lookup).

    Handles view inheritance: child inherits parent's fields, then overrides.
    """
    raw_views = domain_yaml_raw.get("views", {})
    if not raw_views or not isinstance(raw_views, dict):
        return {}

    compiled: Dict[str, ViewDefinition] = {}

    def _resolve(role: str, seen: set) -> ViewDefinition:
        if role in compiled:
            return compiled[role]
        if role in seen:
            logger.warning("Circular view inheritance: %s", seen)
            return {}
        seen.add(role)

        raw = raw_views.get(role)
        if not raw:
            return {}

        parent = raw.get("extends", "")
        base: ViewDefinition = {}
        if parent:
            base = _resolve(parent, seen.copy())

        merged: ViewDefinition = {
            "label": raw.get("label", role),
            "terminology": {},
            "visible_classes": (raw.get("visible_classes") or base.get("visible_classes") or []),
            "hidden_fields": {},
            "default_filters": {},
        }

        base_term = base.get("terminology") or {}
        role_term = raw.get("terminology") or {}
        merged["terminology"] = {**base_term, **role_term}

        base_hidden = base.get("hidden_fields") or {}
        role_hidden = raw.get("hidden_fields") or {}
        merged["hidden_fields"] = {}
        all_fields = set(base_hidden.keys()) | set(role_hidden.keys())
        for f in all_fields:
            merged["hidden_fields"][f] = list(set(
                (base_hidden.get(f) or []) + (role_hidden.get(f) or [])
            ))

        base_filters = base.get("default_filters") or {}
        role_filters = raw.get("default_filters") or {}
        merged["default_filters"] = {**base_filters, **role_filters}

        compiled[role] = merged
        return merged

    for role in raw_views:
        _resolve(role, set())

    return compiled


def resolve_term(term: str, role: str, compiled_views: Dict[str, ViewDefinition]) -> Optional[str]:
    u"""Get the role-specific definition of a term. Returns None if not defined."""
    view = compiled_views.get(role)
    if not view:
        return None
    terminology = view.get("terminology", {})
    term_def = terminology.get(term)
    if term_def:
        return term_def.get("definition", "") if isinstance(term_def, dict) else str(term_def)
    return None


def filter_visible_classes(
    classes: Dict[str, Any],
    role: str,
    compiled_views: Dict[str, ViewDefinition],
) -> Dict[str, Any]:
    u"""Filter a classes dict to only those visible to the given role.

    If no view defined for the role, returns all classes (backwards compatible).
    """
    view = compiled_views.get(role)
    if not view:
        return classes

    visible = view.get("visible_classes", [])
    if not visible:
        return classes  # no restriction

    return {k: v for k, v in classes.items() if k in visible}


def filter_hidden_fields(
    class_name: str,
    class_data: Dict[str, Any],
    role: str,
    compiled_views: Dict[str, ViewDefinition],
) -> Dict[str, Any]:
    u"""Remove hidden fields from class_data for the given role.

    Filters: required_fields, optional_fields, fields[].
    """
    view = compiled_views.get(role)
    if not view:
        return class_data

    hidden = view.get("hidden_fields", {}).get(class_name, [])
    if not hidden:
        return class_data

    result = dict(class_data)
    result["required_fields"] = [f for f in result.get("required_fields", []) if f not in hidden]
    result["optional_fields"] = [f for f in result.get("optional_fields", []) if f not in hidden]
    if "fields" in result:
        result["fields"] = [f for f in result["fields"] if f.get("name") not in hidden]
    return result


def list_roles(compiled_views: Dict[str, ViewDefinition]) -> List[Dict[str, Any]]:
    u"""Return list of all defined roles with their labels."""
    return [
        {"role": role, "label": view.get("label", role)}
        for role, view in sorted(compiled_views.items())
    ]


def validate_views(domain_yaml_raw: Dict[str, Any]) -> Dict[str, Any]:
    u"""Validate views section: check for missing references, broken inheritance, etc."""
    raw_views = domain_yaml_raw.get("views", {})
    classes = set((domain_yaml_raw.get("classes") or {}).keys())
    issues = []

    for role, view in raw_views.items():
        visible = view.get("visible_classes", [])
        for cls_name in visible:
            if cls_name not in classes:
                issues.append(f"View '{role}': visible_class '{cls_name}' not found in domain classes")

        hidden = view.get("hidden_fields", {})
        for cls_name in hidden:
            if cls_name not in classes:
                issues.append(f"View '{role}': hidden_fields for '{cls_name}' — class not found")

        parent = view.get("extends", "")
        if parent and parent not in raw_views:
            issues.append(f"View '{role}': extends '{parent}' — parent view not found")

    return {"valid": len(issues) == 0, "issues": issues}
