"""Audit Rules — domain-agnostic YAML-driven operator engine.

Phase 20: loads audit_rules from domain YAML ontology files and applies
standardized operators (gt/lt/eq/in/contains/regex) to match agent decisions.
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List

# ── Standardized operator set ──

_OPERATORS = {
    "gt": lambda v, t: float(v) > t,
    "lt": lambda v, t: float(v) < t,
    "eq": lambda v, t: str(v) == str(t),
    "in": lambda v, t: str(v) in [str(x) for x in t],
    "contains": lambda v, t: str(t) in str(v),
    "regex": lambda v, t: bool(_re.search(str(t), str(v))),
}


def load_audit_rules(domain_id: str) -> List[Dict[str, Any]]:
    """Load audit_rules from domain YAML file."""
    import os as _os
    import yaml as _yaml

    onto_dir = _os.path.expanduser("~/.aiplat/ontologies")
    yaml_path = _os.path.join(onto_dir, f"{domain_id}.yaml")
    if not _os.path.exists(yaml_path):
        return []
    data = _yaml.safe_load(open(yaml_path)) or {}
    return data.get("audit_rules", [])


def match_rule_triggers(decision_data: Dict[str, Any], triggers: List[Dict]) -> bool:
    """Check if decision_data matches ALL triggers (AND logic)."""
    for trigger in triggers:
        field = trigger.get("field", "")
        operator = trigger.get("operator", "")
        target = trigger.get("value")

        if operator not in _OPERATORS:
            return False

        field_value = _resolve_field(decision_data, field)
        try:
            if not _OPERATORS[operator](field_value, target):
                return False
        except (ValueError, TypeError):
            return False

    return len(triggers) > 0


def _resolve_field(data: Dict[str, Any], field_path: str) -> Any:
    """Resolve dot-separated field path in nested dict."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, "")
        else:
            return ""
    return current
