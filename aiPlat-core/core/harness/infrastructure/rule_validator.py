"""
Rule Validator (Phase 2, 2026-07-30) — lightweight OWL-RL-style consistency checker.

Checks inference_rules from domain YAML for:
  - exclusive_states: mutually exclusive state groups
  - state_dependencies: required entity attributes before entering a state

Integrating into ActionRegistry Step 3.5 prevents rule-violating transitions.
"""
from __future__ import annotations

import logging
import os
import yaml
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RuleValidator:
    """Domain-specific rule checker powered by inference_rules in YAML."""

    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict:
        yaml_path = os.path.expanduser(f"~/.aiplat/ontologies/{self.domain_id}.yaml")
        if not os.path.exists(yaml_path):
            return {}
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("inference_rules", {}) or {}
        except Exception:
            logger.debug("Failed to load rules for %s", self.domain_id, exc_info=True)
            return {}

    def check_transition(
        self, entity_id: str, from_state: str, to_state: str
    ) -> Dict[str, Any]:
        """Check if a state transition violates any inference_rules.

        Returns: {valid: bool, conflicts: [{rule, reason}], constraint_type: "rule"}
        """
        conflicts: List[Dict[str, str]] = []

        # 1. Exclusive states — cannot transition within same group
        exclusive_groups = self.rules.get("exclusive_states", [])
        for group in exclusive_groups:
            if isinstance(group, list) and from_state in group and to_state in group:
                conflicts.append({
                    "rule": f"exclusive_states: {group}",
                    "reason": f"Cannot transition between mutually exclusive states: "
                              f"'{from_state}' → '{to_state}'"
                })

        # 2. State dependencies — must have required attributes
        deps = self.rules.get("state_dependencies", {})
        if to_state in deps:
            required = deps[to_state].get("requires", [])
            if required:
                try:
                    from core.harness.ontology_engine.graph_index import GraphIndex
                    g = GraphIndex.load(self.domain_id)
                    node = g._nodes.get(entity_id)
                    if not node:
                        conflicts.append({
                            "rule": f"state_dependencies: {to_state}",
                            "reason": f"Entity {entity_id} not found, cannot verify dependencies"
                        })
                    else:
                        metadata = getattr(node, 'metadata', {}) or {}
                        missing = [r for r in required if r not in metadata or not metadata[r]]
                        if missing:
                            conflicts.append({
                                "rule": f"state_dependencies: {to_state}",
                                "reason": f"Missing required attributes for state '{to_state}': {missing}"
                            })
                except Exception:
                    logger.debug("Dependency check failed for %s", entity_id, exc_info=True)

        return {
            "valid": len(conflicts) == 0,
            "conflicts": conflicts,
            "constraint_type": "rule" if conflicts else "",
        }
